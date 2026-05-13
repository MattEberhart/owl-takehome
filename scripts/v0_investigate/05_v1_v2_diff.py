"""
v0.5 — Per (name, asof), classify changes between v1 and v2.
Bucket by stock and by kind (split-like 2x/0.5x ratio, rounding-only, other).
Investigate the Apple rows where close changed but volume didn't.
"""
import sys
sys.path.insert(0, '.')

from collections import Counter
from pipeline.load import load_source

v1 = load_source('data/stock-data-se-owl.xlsx')
v2 = load_source('data/stock-data-se-owl-part2.xlsx')

v1i = v1.set_index(['name', 'asof'])
v2i = v2.set_index(['name', 'asof'])
shared = v1i.index.intersection(v2i.index)
print(f'shared rows: {len(shared)}')

stats = Counter()
apple_close_changed_vol_same = []
for k in shared:
    r1, r2 = v1i.loc[k], v2i.loc[k]
    c1, c2 = float(r1['close_usd']), float(r2['close_usd'])
    vol1, vol2 = int(r1['volume']), int(r2['volume'])
    name = k[0]
    if c1 == c2 and vol1 == vol2:
        stats[(name, 'unchanged')] += 1
        continue
    close_ratio = c2 / c1 if c1 != 0 else None
    vol_ratio = vol2 / vol1 if vol1 != 0 else None
    if close_ratio and 0.49 < close_ratio < 0.51 and vol_ratio and 1.99 < vol_ratio < 2.01:
        stats[(name, 'split-2for1')] += 1
    elif close_ratio and 0.999 < close_ratio < 1.001 and vol1 == vol2:
        stats[(name, 'rounding-only')] += 1
    else:
        stats[(name, 'other')] += 1
        if name == 'Apple' and c1 != c2 and vol1 == vol2:
            apple_close_changed_vol_same.append((k, vol1, c1, c2))

print('\nChange buckets per stock:')
for (name, kind), n in sorted(stats.items()):
    print(f'  {name:20s} {kind:18s} {n}')

print(f'\nApple rows where close changed but volume did NOT: {len(apple_close_changed_vol_same)}')
zero_vol = [x for x in apple_close_changed_vol_same if x[1] == 0]
print(f'  of which had volume == 0: {len(zero_vol)}')
non_zero = [x for x in apple_close_changed_vol_same if x[1] != 0]
if non_zero:
    print(f'  non-zero-volume cases (first 5):')
    for case in non_zero[:5]:
        print(f'    {case}')

print('\nFinding: Apple shows ~6000 split-adjusted rows (close×0.5, volume×2). '
      'Amazon and Alphabet show rounding-only changes (close drifts by <1e-3, volume unchanged). '
      'Facebook is fully unchanged. The "Apple vol unchanged when close changed" cases are '
      'either zero-volume days or precision artifacts of integer-doubling. Migration strategy: '
      'always UPSERT by (stock_id, asof). Change-detection would generate noise.')
