"""
Database connection + migration runner.

Migrations live in ./migrations/ as `NNNN_description.sql`. The runner
applies any whose `NNNN` is not yet recorded in `_meta_schema_version`.
Each migration is applied inside a single transaction; if anything fails,
nothing is committed.

We boot the meta table by hand (chicken-and-egg: we can't query it before
migration 0001 has created it).
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / 'migrations'
_FILENAME_RE = re.compile(r'^(\d{4})_.+\.sql$')


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    """Return the set of applied versions, or empty if the meta table doesn't exist yet."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='_meta_schema_version'"
    )
    if cur.fetchone() is None:
        return set()
    return {row[0] for row in conn.execute('SELECT version FROM _meta_schema_version')}


def _discover_migrations() -> list[tuple[int, Path]]:
    """All numbered migration SQL files in NNNN_description.sql form, sorted ascending."""
    out: list[tuple[int, Path]] = []
    for p in sorted(MIGRATIONS_DIR.iterdir()):
        m = _FILENAME_RE.match(p.name)
        if m:
            out.append((int(m.group(1)), p))
    return out


def run_migrations(conn: sqlite3.Connection) -> list[int]:
    """
    Apply any pending migrations. Returns the list of versions that were
    applied in this call (empty list = nothing to do = idempotent re-run).
    """
    applied = _applied_versions(conn)
    pending = [(v, p) for v, p in _discover_migrations() if v not in applied]
    newly_applied: list[int] = []

    for version, path in pending:
        sql = path.read_text()
        try:
            with conn:  # transaction
                conn.executescript(sql)
                conn.execute(
                    'INSERT INTO _meta_schema_version (version) VALUES (?)',
                    (version,),
                )
        except Exception:
            raise RuntimeError(f'Migration {version} ({path.name}) failed') from None
        newly_applied.append(version)

    return newly_applied
