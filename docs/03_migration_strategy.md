# Migration strategy

Two distinct flavors of "migration" show up in this pipeline:

1. **Schema migrations** — adding/altering tables and columns. Handled by numbered SQL files in `migrations/` and the runner in `pipeline/db.py`.
2. **Data migrations** — in-place updates to existing rows (e.g. v2's Apple split adjustment, Amazon/Alphabet decimal re-rounding). Handled by UPSERT on the natural key.

Both flavors are idempotent: running the pipeline twice produces the same database state.

## Schema migrations

Files: `migrations/NNNN_description.sql`, applied in ascending numeric order.

Algorithm (in `pipeline/db.py::run_migrations`):

```
1. Read applied versions from _meta_schema_version (empty set if the table
   doesn't exist yet — chicken-and-egg bootstrap).
2. For each on-disk migration file whose number is not in the applied set:
     a. BEGIN transaction
     b. executescript() the file
     c. INSERT INTO _meta_schema_version (version) VALUES (...)
     d. COMMIT (or ROLLBACK on any exception)
3. Return the list of newly-applied versions.
```

Why hand-rolled and not Alembic:

- Two migrations and ~30 lines of runner code. Alembic adds a SQLAlchemy dependency and a config surface for no benefit at this scale.
- Migrations are pure SQL files — easy to inspect/diff/review. No autogen mystery.
- Transactional. A partial migration leaves nothing behind.

### Migration 0001 — initial schema

Creates `_meta_schema_version`, `stock`, `sector`, `stock_sector_assignment`, `stock_price`.

### Migration 0002 — add `mktcap_usd`

```sql
ALTER TABLE stock_price ADD COLUMN mktcap_usd REAL;
```

The column is nullable. Existing rows are backfilled when the pipeline re-runs against the v2 source: the UPSERT path picks up `mktcap_usd` automatically when the source has it *and* the column has been added.

## Data migrations (UPSERT)

Idempotency comes from the natural key, not from change detection. Every ingest is an UPSERT:

```sql
INSERT INTO stock_price (stock_id, asof, close_usd, volume, mktcap_usd)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(stock_id, asof) DO UPDATE SET
  close_usd  = excluded.close_usd,
  volume     = excluded.volume,
  mktcap_usd = excluded.mktcap_usd;
```

This handles all of:
- **First load**: zero conflicts → pure INSERT.
- **Re-run on unchanged input**: every row conflicts → DO UPDATE writes identical values → effective no-op.
- **Apple's 2-for-1 split (v1 → v2)**: every Apple row conflicts → DO UPDATE writes the halved-close, doubled-volume values.
- **Amazon/Alphabet rounding-only changes (v1 → v2)**: row conflicts → DO UPDATE writes the re-rounded close.
- **New `mktcap_usd` column**: once migration 0002 has run, the same UPSERT path now sets `mktcap_usd` from the source.

Why not "detect changes, then update only those rows"? Two reasons:
- **Fragile**: v2's Amazon/Alphabet decimal re-rounding would generate a flood of false-positive "changes" that aren't conceptually changes.
- **Same cost**: SQLite executes the upsert plan in a single B-tree probe regardless of whether the values changed. Detect-then-update buys nothing.

## Operator-driven rename handling (planned `stock_alias`)

The pipeline does not auto-detect renames. If a v3 source shipped `"Meta Class A"` instead of `"Facebook Class A"`, the pipeline would create a *new* `stock` row — there's no way for it to *know* that's a rename without an external stable id (CUSIP/ISIN/ticker).

The planned future shape is an operator-populated alias table:

```sql
CREATE TABLE stock_alias (
  stock_id        INTEGER NOT NULL REFERENCES stock(id),
  alias_name      TEXT    NOT NULL,
  effective_from  TEXT    NOT NULL,
  source          TEXT    NOT NULL,   -- 'operator-decision', 'cusip-match', etc.
  PRIMARY KEY (alias_name)
);
```

This is the right shape because it acknowledges that rename detection is a human decision — the table records those decisions *auditably* rather than pretending the pipeline figured it out. The ingest path would consult `stock_alias` before treating an unknown name as a new stock.

Operator merge procedure for the Facebook → Meta case (until `stock_alias` exists):

```sql
BEGIN;
  -- Find the new and old stock ids.
  -- Assume :old_id = 3 (Facebook Class A), :new_id = 5 (Meta Class A, just inserted by the pipeline).
  UPDATE stock_price
     SET stock_id = :old_id
   WHERE stock_id = :new_id;
  UPDATE stock_sector_assignment
     SET stock_id = :old_id
   WHERE stock_id = :new_id;
  DELETE FROM stock WHERE id = :new_id;
  -- Optionally rename:
  -- UPDATE stock SET name = 'Meta Class A' WHERE id = :old_id;
COMMIT;
```

Critically: **no historical data is destroyed**. Prices and sector assignments are simply repointed.

## Why this design holds up at scale

- **Postgres swap**: `ON CONFLICT ... DO UPDATE` is identical in Postgres. The migration runner pattern works unchanged. Only `executescript` needs to become `cursor.execute()` per statement (Postgres doesn't have executescript).
- **Bulk ingest**: swap pandas-driven `executemany` for `COPY ... FROM STDIN` and the same idempotency contract holds via an `INSERT ... ON CONFLICT` post-load step.
- **Partitioning**: `stock_price` partitioned by year (or stock) doesn't change the UPSERT semantics; it just changes which physical partition the conflict probe lands in.
- **Corporate-action remodel**: the `corporate_action` table (splits/dividends/issuances) would let us *derive* adjusted prices on read instead of relying on silent source-side adjustments. That's a bigger refactor, but the current schema doesn't fight it — it'd add a new table and a view; the existing tables remain.
