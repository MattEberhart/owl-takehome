-- v2 source added a mktcap_usd column. Add it as a nullable column on
-- stock_price. Existing rows stay NULL until the pipeline re-runs against
-- a source that supplies mktcap_usd — the UPSERT path then backfills.

ALTER TABLE stock_price ADD COLUMN mktcap_usd REAL;
