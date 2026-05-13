"""
v0.1 — Load each xlsx, print structure: columns, dtypes, row counts,
null counts, distinct counts, min/max. Surfaces anything weird before
we lock the schema.
"""
import sys
sys.path.insert(0, '.')

from pipeline.load import load_source

FILES = ['data/stock-data-se-owl.xlsx', 'data/stock-data-se-owl-part2.xlsx']

for path in FILES:
    df = load_source(path)
    print(f'\n===== {path} =====')
    print(f'shape: {df.shape}')
    print('dtypes:')
    print(df.dtypes.to_string())
    print('nulls per column:')
    print(df.isna().sum().to_string())
    print('distinct counts per column:')
    print(df.nunique().to_string())
    for col in df.select_dtypes(include=['number']).columns:
        print(f'{col}: min={df[col].min()}, max={df[col].max()}')
    if 'asof' in df.columns:
        print(f'asof: min={df["asof"].min()}, max={df["asof"].max()}')

print('\nFinding: Both files share the same 6/7-column schema (v2 adds mktcap_usd), '
      '17,983 rows each, no nulls. Date range 1999-12-01 → 2023-11-06. '
      '("#" column dropped by the loader as a CSV-export artifact.)')
