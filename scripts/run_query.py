"""
Run the cumulative-return example query and print the result as a table.

Usage:
    python -m scripts.run_query --db owl.sqlite
    python -m scripts.run_query --db owl.sqlite --query queries/cumulative_return.sql
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, '.')

DEFAULT_QUERY = 'queries/cumulative_return.sql'


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--db', default='owl.sqlite')
    p.add_argument('--query', default=DEFAULT_QUERY)
    args = p.parse_args(argv)

    sql = Path(args.query).read_text()
    conn = sqlite3.connect(args.db)
    try:
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        widths = [max(len(c), max((len(str(r[i])) for r in rows), default=0)) for i, c in enumerate(cols)]
        print(' | '.join(c.ljust(w) for c, w in zip(cols, widths)))
        print('-+-'.join('-' * w for w in widths))
        for r in rows:
            print(' | '.join(str(v).ljust(w) for v, w in zip(r, widths)))
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
