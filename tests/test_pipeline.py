"""
End-to-end pipeline tests.

These exercise the full ingest path against the real source xlsx files and
the schema. They use a fresh tmp DB per test so they don't depend on or
disturb any local owl.sqlite.

Covers:
  - migration 0001 applies cleanly to a fresh DB
  - first ingest of v1 produces the expected row counts and assignment
  - re-running the pipeline on v1 is a no-op (idempotency on unchanged input)
  - the cumulative-return query returns 4 rows matching the smoke target
  - applying v2 in-place after v1: row count unchanged, Apple close halved,
    mktcap_usd populated everywhere
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pipeline.db import connect, run_migrations
from pipeline.ingest import ingest
from pipeline.load import load_source

V1 = 'data/stock-data-se-owl.xlsx'
V2 = 'data/stock-data-se-owl-part2.xlsx'
CUMULATIVE_RETURN_SQL = Path('queries/cumulative_return.sql').read_text()


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / 'test.sqlite')
    yield conn
    conn.close()


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        t: conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        for t in ['stock', 'sector', 'stock_sector_assignment', 'stock_price']
    }


def test_v1_load_produces_expected_shape(db):
    run_migrations(db)
    ingest(db, load_source(V1))
    assert _counts(db) == {
        'stock': 4,
        'sector': 3,
        'stock_sector_assignment': 4,
        'stock_price': 17_983,
    }


def test_v1_load_is_idempotent(db):
    run_migrations(db)
    df = load_source(V1)
    ingest(db, df)
    first = _counts(db)
    first_sum_close = db.execute('SELECT SUM(close_usd) FROM stock_price').fetchone()[0]

    ingest(db, df)
    second = _counts(db)
    second_sum_close = db.execute('SELECT SUM(close_usd) FROM stock_price').fetchone()[0]

    assert first == second
    assert first_sum_close == second_sum_close


def test_cumulative_return_query_matches_smoke_targets(db):
    run_migrations(db)
    ingest(db, load_source(V1))
    rows = db.execute(CUMULATIVE_RETURN_SQL).fetchall()
    by_name = {r[0]: r for r in rows}

    # Targets from scripts/v0_investigate/07_returns_smoke.py
    expected = {
        'Apple': 193.772609,
        'Amazon Com': 31.880002,
        'Facebook Class A': 7.260141,
        'Alphabet Class C': 3.627061,
    }
    assert set(by_name) == set(expected)
    for name, target in expected.items():
        cum_return = by_name[name][-1]
        assert cum_return == pytest.approx(target, rel=1e-5), name


def test_v2_migration_and_in_place_updates(db):
    # Baseline: load v1.
    run_migrations(db)
    ingest(db, load_source(V1))
    pre_apple_close_sum = db.execute(
        "SELECT SUM(close_usd) FROM stock_price WHERE stock_id = "
        "(SELECT id FROM stock WHERE name = 'Apple')"
    ).fetchone()[0]
    pre_count = _counts(db)

    # Migrate to v2 schema and ingest the v2 source. With migration 0002
    # present, run_migrations() in this pass is a no-op (already applied);
    # the column was already added on the initial call above. ingest()
    # picks up mktcap_usd because source has it and column exists.
    run_migrations(db)
    ingest(db, load_source(V2))

    post_count = _counts(db)
    assert pre_count == post_count, 'v2 should not add or remove rows'

    # Apple: close halved across every row -> sum is halved.
    post_apple_close_sum = db.execute(
        "SELECT SUM(close_usd) FROM stock_price WHERE stock_id = "
        "(SELECT id FROM stock WHERE name = 'Apple')"
    ).fetchone()[0]
    assert post_apple_close_sum == pytest.approx(pre_apple_close_sum / 2, rel=1e-6)

    # mktcap_usd column exists and every row is populated.
    cols = {row[1] for row in db.execute('PRAGMA table_info(stock_price)')}
    assert 'mktcap_usd' in cols
    non_null = db.execute(
        'SELECT COUNT(*) FROM stock_price WHERE mktcap_usd IS NOT NULL'
    ).fetchone()[0]
    total = db.execute('SELECT COUNT(*) FROM stock_price').fetchone()[0]
    assert non_null == total

    # Re-running ingest on v2 is still idempotent (row counts and SUMs stable).
    ingest(db, load_source(V2))
    assert _counts(db) == post_count
    again = db.execute(
        "SELECT SUM(close_usd) FROM stock_price WHERE stock_id = "
        "(SELECT id FROM stock WHERE name = 'Apple')"
    ).fetchone()[0]
    assert again == post_apple_close_sum
