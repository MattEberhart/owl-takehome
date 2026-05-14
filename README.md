# Owl SSE Take-Home — Stock Data Pipeline

## Matt's Comments
Claude wrote the code so I wanted to give you all a sense of how I thought through this problem before I let it start writing.

After reading through the assignment the first thing I did was look at the denormalized columns in your source data. I immediately clocked the repeated values for company name and sector columns as something to normalize away. No need to repeat store these for every day of stock data.

A simple solution was to have a stock entity with name and foreign key to sectors entity. Then a prices entity with a foreign key to the stock, but I had additional questions.

1. What happens when stock names change? (Facebook -> Meta)
2. What happens when sector changes? (Amazon Consumer/Retailer -> Technology/Hyperscaler)
3. What is a sector? Will there be a level 3 down the road? Can a stock have multiple l1/l2 assignments at a time?
4. How do we handle market cap? It is a function of closing price and number of shares. Source does not provide number of shares, but my instinct is usually to store primitives and derive metrics.

About here is where I gave my initial prompt to claude to analyze the data, task, and my initial proposals / concerns. Claude analyzed the data and found stock names didn't change (other than minor extra space hygeine issues), sectors didn't change, and it hyperfocused on the 2 hour limit in the task. Because of this it really pushed for the simple solution I mentioned above. I had to argue with it about the following:

### RE: Stock names changing
At one point I considered having a names table with foreign key to the stock entity. This left my stock entity with just an id which felt super wrong. It could have had a current name/ticker that was separately tracked. I also realized having this was not a dynamic fix anyways - I'd have to pre populate the names table and foreign keys to the stock. It was over engineering for a problem not in the dataset yet that doesn't happen often in real life so I settled with name in the stock table. I noted a future migration in /docs to have a name alias table to account for this gap.

### RE: Sector questions
Claude also found with a script that sector values were not changing, but this struck me as a more common problem. I imagine sectors change and new ones are probably invented pretty often. I though of and evaluated a few approaches. I was less familiar with this field than I was with close price, market cap, and volume so I did some research as well and found GICS standard is a 4 level sector and each stock has one combination assigned, so I wanted to solve for adding more levels later. 
1. Nested sector table where each row had a fk to it's parent. Stock has an fk to it's most child sector. This did not allow for historical sector tracking and required self joins per level. 
2. Flat sectors table where there is a column for each level. Each row should be a unique combination. Duplicates top level values, but avoids that self join I was talking about. I was still thinking fk from stock which didn't allow for historical tracking. Adding a level is a simple column add + some business logic about how to handle existing 2 level sectors.
3. Either of the above, but with the stock_sector_assignment table. This table represents the sector assignment along with an effective from date. Joining this with stocks and sectors then filtering on effective from date can give you the sector of a stock for any given historical date.

I decided on the flat structure to avoid self joins and have a simpler future additional level migration along with the assignment table for historical sector tracking. This is probably overkill for this dataset, but it seemed like important planning for me.

### RE: market cap
Here I just worked with what I had. My brain still wants to have a number of shares to derive this for some reason. We can still derive the other way I guess. Market cap just goes on the stock_price entity since it is also a per day value.

### Idempotency
For each row in the source data we clean the name and use it to get a stock id. We use the stock id + the asof date as a key to upsert close price, volume, and market cap. Similarly we use the stock id (gathered from cleaned name) and sector combination to upsert a sector assignment. Found a bug as I wrote this, fixed in commit 3.

A question I have as I'm writing this is if a dataset is full every time? The idempotency I explained above handles the stock split if so. Just overwrite the closing price and market cap across all the records. If the latest run has a stock split and only data from the past few years, I am overwriting the latest years according to the stock split and previous years remain unsplit - bad. I'm assuming each run is complete since we are handling split data as a whole set and not as some event we subscribe to and fix.

### Stack
pandas to turn csv (or xlsv) to a manipulatable dataframe. load.py reads in and cleans data. ingest.py does the idempotent upserts based on the key logic above.

sqlite for local simple to setup relational db. 

## Below Here is Claude generated, Matt reviewed

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

## Ad hoc queries

Run any SQL file through the formatted printer:

```bash
python -m scripts.run_query --db owl.sqlite --query queries/cumulative_return.sql
```

Or hit the SQLite file directly for one-off queries:

```bash
# Interactive shell
sqlite3 owl.sqlite

# One-liner, column headers + aligned output
sqlite3 -header -column owl.sqlite 'SELECT * FROM stock LIMIT 5;'

# Inspect the schema
sqlite3 owl.sqlite '.schema'
```

## Reset the local database

The SQLite database is just a file. To start over from scratch:

```bash
rm -f owl.sqlite
```

The next `python -m scripts.run_pipeline …` invocation will re-apply every migration from `0001` onward and reload from source. `owl.sqlite` is gitignored, so this is always safe.

To reset only the data without re-running migrations:

```bash
sqlite3 owl.sqlite 'DELETE FROM stock_price; DELETE FROM stock_sector_assignment; DELETE FROM sector; DELETE FROM stock;'
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
