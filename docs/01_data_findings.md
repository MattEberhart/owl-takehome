# Data findings (v0 investigation)

Output of `scripts/v0_investigate/*.py` against both source xlsx files. These checks ran *before* schema was committed and informed several design choices in `02_schema.md`.

## File shape

| File | Rows | Cols | Date range | Nulls | Dup `(name, asof)` |
|---|---|---|---|---|---|
| `data/stock-data-se-owl.xlsx` (v1) | 17,983 | 7 (incl. `#`) | 1999-12-01 → 2023-11-06 | 0 | 0 |
| `data/stock-data-se-owl-part2.xlsx` (v2) | 17,983 | 8 (`#` + `mktcap_usd`) | same | 0 | 0 |

The `#` column is a CSV-export row index, not data. `pipeline/load.py` drops it.

## Stocks

Four: `Alphabet Class C`, `Amazon Com`, `Apple`, `Facebook Class A ` (← trailing space). The loader strips on ingest.

Row counts per stock (same in both files):

| Stock | Rows | First asof |
|---|---|---|
| Amazon Com | 6,244 | 1999-12-01 |
| Apple | 6,244 | 1999-12-01 |
| Facebook Class A | 2,992 | 2012-05-18 |
| Alphabet Class C | 2,503 | 2014-04-03 |

## Sectors

| sector_level1 | sector_level2 |
|---|---|
| Technology | Software & IT Services |
| Technology | Technology Equipment |
| CONSUMER CYCLICALS | Retailers |

L2 → L1 is functional (each L2 has exactly one L1 parent). Each stock has exactly *one* `(L1, L2)` pair across its entire timeline — **no GICS-style reclassifications in the data**. The source appears to apply current classifications retroactively. The `stock_sector_assignment` table starts with one row per stock, but the schema supports adding future reclassifications additively.

## v1 → v2 changes

`(name, asof)` is identical between v1 and v2 — v2 is a pure in-place revision, not an expansion. Per-stock change buckets:

| Stock | unchanged | split-2for1 | rounding-only | other |
|---|---|---|---|---|
| Apple | 0 | **6,021** | 0 | **223** |
| Amazon Com | 3,586 | 0 | 2,658 | 0 |
| Alphabet Class C | 341 | 0 | 2,162 | 0 |
| Facebook Class A | 2,992 | 0 | 0 | 0 |

- **Apple "split-2for1"** = `close_usd × 0.5`, `volume × 2`. The headline transformation called out in the assignment.
- **Apple "other" = 223 rows, all with `volume == 0`**. These are zero-volume days (weekends or pre-IPO gaps in the source) where `volume × 2 = 0` still, but the close was halved. Not a data-quality issue; expected behavior.
- **Amazon/Alphabet "rounding-only"** = `close_usd` changes by < 1e-3 (e.g. `2.80078125 → 2.800781`), volume unchanged. Looks like the source was re-emitted with fewer decimal places. Naive change-detection would generate false positives here.
- **Facebook** is fully unchanged.

→ **Migration must always UPSERT by `(stock_id, asof)`. Change-detection-then-update would generate noise from the rounding-only changes.**

## mktcap_usd

Present on all 17,983 v2 rows, zero nulls. Range: `1.82e9` → `1.96e12`.

Implied shares = `mktcap_usd / close_usd` for each stock's latest row:

| Stock | Implied shares (latest) |
|---|---|
| Apple | ~15.5 B |
| Amazon | ~10.5 B |
| Alphabet C | ~5.7 B |
| Facebook A | ~2.5 B |

These match real-world share counts. The mktcap is invariant to the Apple 2-for-1 split (close halves, implied shares double, product unchanged) — confirming it's a *standalone fact*, not derivable from anything else we store.

## Cumulative returns (v1, smoke target)

`(latest_close - earliest_close) / earliest_close` from v0.7:

| Stock | First → Last | Cumulative return |
|---|---|---|
| Apple | 1999-12-01 → 2023-11-06 | **193.77** (≈ 19,377%) |
| Amazon | 1999-12-01 → 2023-11-06 | 31.88 |
| Facebook | 2012-05-18 → 2023-11-06 | 7.26 |
| Alphabet C | 2014-04-03 → 2023-11-06 | 3.63 |

These are the target numbers the SQL example query (`queries/cumulative_return.sql`) must match.

## Decisions this validates

| Hypothesis | Validated? | Note |
|---|---|---|
| `(name, asof)` is the natural key | ✓ | No dups, identical key sets in v1/v2 |
| Whitespace-strip name on ingest | ✓ | Facebook trailing space in both files |
| `stock_sector_assignment` is justified | ✓ in principle | But initial table has 1 row per stock — assignment is forward-compatible with future reclassifications, not exercised by current data |
| mktcap as a column on `stock_price` | ✓ | Source provides it, it's invariant to split, no derivability issues |
| UPSERT idempotency by natural key | ✓ | Required: v2's rounding-only changes break change-detection |
