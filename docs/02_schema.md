# Schema

## Tables

```
stock                       sector
┌────────┐                  ┌──────┐
│ id PK  │                  │ id PK│
│ name UQ│                  │ l1   │
└───┬────┘                  │ l2 UQ│ (UNIQUE(l1, l2))
    │                       └──┬───┘
    │                          │
    │   ┌──────────────────────┘
    │   │
┌───▼───▼─────────────────┐
│ stock_sector_assignment │
│   stock_id    FK ──┐    │   PK (stock_id, effective_from)
│   sector_id   FK ──┘    │   "Current sector" = MAX(effective_from)
│   effective_from        │   Reclassifications are additive INSERTs.
└─────────────────────────┘

┌────────────────────────┐
│ stock_price            │   PK (stock_id, asof)
│   stock_id FK          │   UPSERT by PK = idempotency.
│   asof                 │   mktcap_usd added by migration 0002.
│   close_usd            │
│   volume               │
│   mktcap_usd  (NULL OK)│
└────────────────────────┘
```

## GICS grounding

The sector model reflects the Global Industry Classification Standard (S&P / MSCI), which is the dominant equity classification system. Key facts that drove design:

- **4 levels**: 11 sectors → 25 industry groups → 74 industries → 163 sub-industries.
- **1:N**: each company is assigned to exactly *one* sub-industry based on primary revenue source. Bridge tables would be the wrong shape.
- Even diversified conglomerates get a single assignment (Berkshire is Financials; "Multi-Sector Holdings" is itself a single sub-industry).
- **Reclassifications happen.** The 2018 GICS restructuring moved Facebook and Alphabet from Information Technology to Communication Services. This justifies `stock_sector_assignment.effective_from`.

The source data we have applies current classifications retroactively across the full timeline (no in-data reclassifications). In a production system I'd want to know if that's intentional source-side behavior — flagged as a walkthrough talking point.

## Rationale per table

### `stock(id, name UNIQUE)`

Pure identity. The natural-key column from the source (`name`) doubles as the lookup column. There is no history table — see "Alternatives considered" → `stock_name`.

### `sector(id, level1, level2)`

Flat lookup. Three rows for our data. The hierarchy is implicit in `UNIQUE(level1, level2)` plus the functional dependency `level2 → level1`. One join exposes both levels.

### `stock_sector_assignment(stock_id, sector_id, effective_from)`

Temporal link. `effective_from` is an ISO date string; the *current* sector for a stock is the row with the largest `effective_from`. Reclassifications are modeled as additive INSERTs — never UPDATEs. No `effective_to` (computable from successor rows; skipping it avoids SCD2 bookkeeping at this scale).

### `stock_price(stock_id, asof, close_usd, volume, mktcap_usd)`

Wide fact table at the `(stock, day)` grain. New per-day facts arrive as `ALTER TABLE ADD COLUMN`. Primary key `(stock_id, asof)` powers UPSERT idempotency.

## Alternatives considered

Each entry: the alternative, what's appealing about it, why we rejected it.

### Adjacency-list sector: `sector(id, name, parent_id, level)`

Textbook-correct for hierarchies in general. Rejected because GICS is *fixed-depth* (always exactly 4 levels) and *single-taxonomy* — the two situations where adjacency-list earns its keep don't apply. Adjacency-list pays the cost (parent_id walks, recursive CTEs, implicit "assignment points to leaf" convention) without the benefit. Would become the right call if we ever needed a variable-depth taxonomy (some chains shorter than others) or wanted to unify multiple taxonomies in one table.

### Pre-allocating nullable `level3, level4` columns now

Rejected as YAGNI. The columns approach is correct for fixed-depth taxonomies, but adding L3/L4 before data exists invites the NULL-ambiguity problem (depth unknown vs. not applicable vs. data missing) and makes `UNIQUE` constraints weird (NULL ≠ NULL in SQL). When L3 actually arrives, `ALTER TABLE ADD COLUMN level3` + extending `UNIQUE` is a one-line migration. Add columns *when* needed, not *in case* needed.

### `stock_name` history table

Rejected. The pipeline can't auto-detect renames without an external stable id (CUSIP/ISIN/ticker), so a history table would just record operator decisions rather than source-of-truth changes. Theater. The future-proof shape is `stock_alias` (operator-driven), not `stock_name` history. See `03_migration_strategy.md`.

### Foreign key `stock.sector_id` instead of an assignment table

Rejected. Forces destructive UPDATEs on reclassification and loses historical context — the 2018 GICS restructuring would silently rewrite Facebook's pre-2018 sector to Communication Services, erasing the fact that it *was* Tech for years.

### Bridge table `stock_sector(stock_id, sector_id)` (many-to-many, no time)

Rejected. Pays the join cost of M:N without the capability: GICS multi-membership doesn't exist (one sub-industry per company), and history needs `effective_from`. A bridge table without time can model neither.

### Storing `shares_outstanding` instead of `mktcap_usd`, deriving market cap on read

Rejected for precision loss. Real share counts are integers; `mktcap / close` gives a float. Storing the derived value is fine when the source treats it as authoritative, which is the case here. The structurally correct prod answer is a `corporate_action` table (splits, dividends, issuances) that drives a `shares_outstanding` history; adjusted prices fall out of that naturally rather than being silently re-shipped in the source. Out of scope; documented as the prod answer.

### SCD2 with `effective_to` on `stock_sector_assignment`

Rejected as overkill. With one new row per reclassification and no `effective_to`, "current sector" is `MAX(effective_from)` and "sector as of date D" is `MAX(effective_from <= D)`. Both are clean SQL at this scale.

### EAV / "skinny" fact table: `observation(stock_id, asof, metric, value)`

Rejected. Maximally flexible (add new metrics without schema migration) but loses type safety and makes every query require pivots. Wide column-add on `stock_price` is the right tradeoff at this row count.

## Indexes

- `stock_price.PK (stock_id, asof)` — drives UPSERT and per-stock time-range queries.
- `idx_stock_price_asof` — supports cross-stock date queries (e.g. "all close prices on 2023-11-06").
- `stock.name UNIQUE` — drives the ingest lookup.
- `sector.(level1, level2) UNIQUE` — drives the ingest lookup for sectors.

## Future work to call out

- `stock_alias` table (see `03_migration_strategy.md`) for handling renames as operator decisions.
- `corporate_action` table for splits/dividends/issuances, with adjusted prices computed on read. Solves the "v2 silently re-shipped split-adjusted history" problem structurally.
- L3+ sector levels: `ALTER TABLE sector ADD COLUMN level3` when data arrives.
