-- Initial schema for the OWL stock-data pipeline.
-- Applied by pipeline.db.run_migrations() once and recorded in _meta_schema_version.

CREATE TABLE _meta_schema_version (
  version    INTEGER PRIMARY KEY,
  applied_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE stock (
  id   INTEGER PRIMARY KEY,
  name TEXT    NOT NULL UNIQUE
);

CREATE TABLE sector (
  id     INTEGER PRIMARY KEY,
  level1 TEXT    NOT NULL,
  level2 TEXT    NOT NULL,
  UNIQUE (level1, level2)
);

-- One row per (stock, effective_from). Current sector = the row with MAX(effective_from).
-- Designed to support GICS reclassifications additively (no UPDATE needed when a
-- reclassification happens — just INSERT a new row with a later effective_from).
CREATE TABLE stock_sector_assignment (
  stock_id       INTEGER NOT NULL REFERENCES stock(id),
  sector_id      INTEGER NOT NULL REFERENCES sector(id),
  effective_from TEXT    NOT NULL,
  PRIMARY KEY (stock_id, effective_from)
);

CREATE TABLE stock_price (
  stock_id  INTEGER NOT NULL REFERENCES stock(id),
  asof      TEXT    NOT NULL,
  close_usd REAL    NOT NULL,
  volume    INTEGER NOT NULL,
  PRIMARY KEY (stock_id, asof)
);

CREATE INDEX idx_stock_price_asof ON stock_price(asof);
