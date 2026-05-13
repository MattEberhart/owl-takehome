"""
v0.7 — Compute cumulative return per stock from the raw v1 data, so we have a
target answer to validate the SQL query against later.
cumulative_return = (latest_close - earliest_close) / earliest_close
"""
import sys
sys.path.insert(0, '.')

import pandas as pd
from pipeline.load import load_source

df = load_source('data/stock-data-se-owl.xlsx').sort_values(['name', 'asof'])

result = (
    df.groupby('name')
      .apply(lambda g: pd.Series({
          'earliest_asof': g['asof'].iloc[0],
          'earliest_close': g['close_usd'].iloc[0],
          'latest_asof': g['asof'].iloc[-1],
          'latest_close': g['close_usd'].iloc[-1],
          'cumulative_return': (g['close_usd'].iloc[-1] - g['close_usd'].iloc[0]) / g['close_usd'].iloc[0],
      }), include_groups=False)
      .reset_index()
)
print(result.to_string(index=False))

print('\nFinding: Cross-check target for the SQL example query. Same numbers should fall out of '
      'queries/cumulative_return.sql once the pipeline has loaded the v1 data.')
