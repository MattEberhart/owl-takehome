"""
Ingest a cleaned DataFrame (from pipeline.load.load_source) into the DB.

Idempotency strategy: UPSERT by natural key on every table.
  - stock: INSERT OR IGNORE on (name).
  - sector: INSERT OR IGNORE on (level1, level2).
  - stock_sector_assignment: INSERT OR IGNORE on (stock_id, effective_from).
      One row per unique (stock, sector) combination in the source.
      effective_from = earliest asof for that (stock, sector) combination.
      If a stock has multiple sectors across the timeline (reclassification),
      each gets its own assignment row dated to its first appearance.
  - stock_price: INSERT ... ON CONFLICT(stock_id, asof) DO UPDATE with the
      new close_usd / volume / mktcap_usd. The mktcap_usd column is included
      only if the migration that added it has already run *and* the source
      provided the column.

Everything happens inside a single transaction.
"""
from __future__ import annotations

import sqlite3

import pandas as pd


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f'PRAGMA table_info({table})'))


def ingest(conn: sqlite3.Connection, df: pd.DataFrame) -> dict[str, int]:
    """
    Insert/update everything in `df` into the DB.

    Returns a dict of operation counts for observability:
      { 'stocks_seen': int, 'sectors_seen': int, 'assignments_inserted': int,
        'prices_upserted': int }
    """
    source_has_mktcap = 'mktcap_usd' in df.columns
    db_has_mktcap = _column_exists(conn, 'stock_price', 'mktcap_usd')

    stats = {'stocks_seen': 0, 'sectors_seen': 0,
             'assignments_inserted': 0, 'prices_upserted': 0}

    with conn:  # transaction
        # 1. stock — INSERT OR IGNORE by unique name.
        unique_names = df['name'].drop_duplicates()
        conn.executemany(
            'INSERT OR IGNORE INTO stock (name) VALUES (?)',
            [(n,) for n in unique_names],
        )
        stats['stocks_seen'] = len(unique_names)

        # 2. sector — INSERT OR IGNORE by (level1, level2).
        unique_sectors = df[['sector_level1', 'sector_level2']].drop_duplicates()
        conn.executemany(
            'INSERT OR IGNORE INTO sector (level1, level2) VALUES (?, ?)',
            list(unique_sectors.itertuples(index=False, name=None)),
        )
        stats['sectors_seen'] = len(unique_sectors)

        # Build id lookups once after stock/sector inserts.
        stock_id_by_name = dict(conn.execute('SELECT name, id FROM stock'))
        sector_id_by_pair = {
            (l1, l2): sid
            for sid, l1, l2 in conn.execute('SELECT id, level1, level2 FROM sector')
        }

        # 3. stock_sector_assignment — one row per unique (stock, sector) pair
        #    seen in the source. effective_from = earliest asof for THAT
        #    specific (stock, sector) combination, not the stock's overall
        #    earliest asof. This is what makes the table correctly handle a
        #    source that contains a mid-timeline GICS reclassification.
        per_pair = (
            df.groupby(['name', 'sector_level1', 'sector_level2'], as_index=False)['asof']
              .min()
              .rename(columns={'asof': 'effective_from'})
        )
        assignment_rows = [
            (
                stock_id_by_name[r['name']],
                sector_id_by_pair[(r['sector_level1'], r['sector_level2'])],
                r['effective_from'],
            )
            for _, r in per_pair.iterrows()
        ]
        cur = conn.executemany(
            'INSERT OR IGNORE INTO stock_sector_assignment '
            '  (stock_id, sector_id, effective_from) VALUES (?, ?, ?)',
            assignment_rows,
        )
        stats['assignments_inserted'] = cur.rowcount if cur.rowcount != -1 else 0

        # 4. stock_price — UPSERT by (stock_id, asof).
        df_prices = df.copy()
        df_prices['stock_id'] = df_prices['name'].map(stock_id_by_name)

        if source_has_mktcap and db_has_mktcap:
            rows = list(zip(
                df_prices['stock_id'],
                df_prices['asof'],
                df_prices['close_usd'],
                df_prices['volume'],
                df_prices['mktcap_usd'],
            ))
            conn.executemany(
                'INSERT INTO stock_price (stock_id, asof, close_usd, volume, mktcap_usd) '
                'VALUES (?, ?, ?, ?, ?) '
                'ON CONFLICT(stock_id, asof) DO UPDATE SET '
                '  close_usd = excluded.close_usd, '
                '  volume    = excluded.volume, '
                '  mktcap_usd = excluded.mktcap_usd',
                rows,
            )
        else:
            # Either pre-migration (v1) or db has the column but source doesn't —
            # in both cases we just upsert what we have; mktcap stays NULL/unchanged.
            rows = list(zip(
                df_prices['stock_id'],
                df_prices['asof'],
                df_prices['close_usd'],
                df_prices['volume'],
            ))
            conn.executemany(
                'INSERT INTO stock_price (stock_id, asof, close_usd, volume) '
                'VALUES (?, ?, ?, ?) '
                'ON CONFLICT(stock_id, asof) DO UPDATE SET '
                '  close_usd = excluded.close_usd, '
                '  volume    = excluded.volume',
                rows,
            )
        stats['prices_upserted'] = len(rows)

    return stats
