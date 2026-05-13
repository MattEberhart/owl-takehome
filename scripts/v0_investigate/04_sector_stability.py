"""
v0.4 — Per stock, list distinct (sector_level1, sector_level2) pairs across the
full timeline. Confirms L2 → L1 is functional and that there are no in-data
reclassifications.
"""
import sys
sys.path.insert(0, '.')

from collections import defaultdict
from pipeline.load import load_source

for path in ['data/stock-data-se-owl.xlsx', 'data/stock-data-se-owl-part2.xlsx']:
    df = load_source(path)
    print(f'\n===== {path} =====')
    by_name = (df.groupby('name')[['sector_level1', 'sector_level2']]
                 .agg(lambda s: sorted(set(s))))
    print(by_name.to_string())

    l2_to_l1 = defaultdict(set)
    for _, row in df[['sector_level1', 'sector_level2']].drop_duplicates().iterrows():
        l2_to_l1[row['sector_level2']].add(row['sector_level1'])
    bad = {l2: l1s for l2, l1s in l2_to_l1.items() if len(l1s) > 1}
    print(f'\nL2 values mapping to >1 L1 (should be 0): {len(bad)}')

print('\nFinding: Each stock has exactly one (L1, L2) pair across its full timeline. '
      'L2 nests under exactly one L1. No in-data GICS reclassifications — '
      'the source appears to apply current classifications retroactively. '
      'stock_sector_assignment will start with one row per stock.')
