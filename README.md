# Owl SSE Take-Home — Stock Data Pipeline

Normalize denormalized historical stock data (`name, asof, volume, close_usd, sector_*`) into a relational schema, with an idempotent Python pipeline that survives both schema additions (new `mktcap_usd` column) and in-place value revisions (Apple 2-for-1 split adjustment).

See `docs/` for the design rationale and `OWL_SSE_DATA_FINAL.pdf` (in `data/`) for the original prompt.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Commit 1 schema + load v1
python -m scripts.run_pipeline data/stock-data-se-owl.xlsx --db owl.sqlite

# Example query
python -m scripts.run_query --db owl.sqlite

# Commit 2: re-run pipeline against v2 (auto-applies migration 0002, upserts)
python -m scripts.run_pipeline data/stock-data-se-owl-part2.xlsx --db owl.sqlite

# Tests
pytest
```

## Project layout

```
data/         # source xlsx/csv inputs
docs/         # design rationale (read me!)
migrations/   # numbered SQL migrations, applied in order
pipeline/     # db.py, load.py, ingest.py
queries/      # SQL files
scripts/      # CLI entrypoints + v0 investigation scripts
tests/        # pytest
```

## Headline decisions

See `docs/02_schema.md` for the full "Alternatives considered" section. Quick summary:

- **`pandas` + stdlib `sqlite3` + `openpyxl`** — fewest moving parts.
- **`stock(id, name UNIQUE)`** — no name-history table. The pipeline can't auto-detect renames without a stable external id (CUSIP/ISIN/ticker), so a history table would just record operator decisions. Documented future work: `stock_alias`.
- **Flat `sector(id, level1, level2)`** — GICS is fixed-depth (4 levels) and single-taxonomy, so adjacency-list buys nothing. L3/L4 = future `ALTER TABLE ADD COLUMN` when data arrives.
- **`stock_sector_assignment(stock_id, sector_id, effective_from)`** — models real GICS reclassifications (Facebook/Alphabet moved Tech → Communication Services in the 2018 restructuring). Current sector = `MAX(effective_from)`.
- **UPSERT by natural key** for idempotency. Re-running the pipeline on the same input is a no-op; on a revised input it updates in-place.
- **Hand-rolled `_meta_schema_version` + numbered SQL migrations** — no Alembic dependency.

## At scale

- Postgres instead of SQLite; `COPY` for bulk ingest.
- Partition `stock_price` by year.
- `corporate_action` table feeding a `shares_outstanding` history → derive adjusted prices on read rather than relying on silent source-side adjustments.
- dbt for downstream analytics; Great Expectations (or similar) for data-quality contracts.
