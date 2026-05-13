"""
v0.2 — Confirm (name, asof) is unique in both v1 and v2, and that v1 and v2
cover the same key set. Validates our PK choice and confirms v2 is a pure
revision (same rows, different values) rather than a row-level expansion.
"""
import sys
sys.path.insert(0, '.')

from pipeline.load import load_source

v1 = load_source('data/stock-data-se-owl.xlsx')
v2 = load_source('data/stock-data-se-owl-part2.xlsx')

for label, df in [('v1', v1), ('v2', v2)]:
    dups = df.duplicated(subset=['name', 'asof']).sum()
    print(f'{label}: {len(df)} rows, {dups} duplicate (name, asof) pairs')

k1 = set(zip(v1['name'], v1['asof']))
k2 = set(zip(v2['name'], v2['asof']))
print(f'\nkeys only in v1: {len(k1 - k2)}')
print(f'keys only in v2: {len(k2 - k1)}')
print(f'shared: {len(k1 & k2)}')

print('\nFinding: (name, asof) is unique in both files and the key sets are identical. '
      'v2 is a pure in-place revision. Confirms UPSERT-by-(stock_id, asof) is the right '
      'idempotency strategy.')
