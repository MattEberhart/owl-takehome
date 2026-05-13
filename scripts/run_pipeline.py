"""
CLI entry point: load a source file (xlsx or csv), apply any pending
migrations, upsert into the database.

Usage:
    python -m scripts.run_pipeline <source-file> --db <sqlite-file>
"""
from __future__ import annotations

import argparse
import sys

# Allow `python scripts/run_pipeline.py …` in addition to `-m scripts.run_pipeline`.
sys.path.insert(0, '.')

from pipeline.db import connect, run_migrations
from pipeline.ingest import ingest
from pipeline.load import load_source


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description='Idempotently load a stock-data CSV/xlsx into the DB.')
    p.add_argument('source', help='Path to the source file (.csv or .xlsx)')
    p.add_argument('--db', default='owl.sqlite', help='Path to the SQLite database file')
    args = p.parse_args(argv)

    conn = connect(args.db)
    try:
        applied = run_migrations(conn)
        if applied:
            print(f'Applied migrations: {applied}')
        else:
            print('No pending migrations.')

        df = load_source(args.source)
        print(f'Loaded {len(df)} rows from {args.source} (columns: {list(df.columns)})')

        stats = ingest(conn, df)
        print(f'Ingest stats: {stats}')
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
