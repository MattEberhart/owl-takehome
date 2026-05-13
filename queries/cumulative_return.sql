-- Cumulative return per stock from first to last observation in stock_price,
-- joined to stock, the most-recent sector assignment, and the sector taxonomy.
--
-- Exercises:
--   - a real join chain (stock_price → stock → assignment → sector)
--   - an aggregation (MIN/MAX over asof per stock + corresponding closes)
--   - a temporal pick (the "latest" assignment via correlated subquery)
--
-- Output: one row per stock with first-asof close, last-asof close, the
-- assigned sector at last-asof, and the cumulative return.

WITH bounds AS (
  SELECT
    stock_id,
    MIN(asof) AS first_asof,
    MAX(asof) AS last_asof
  FROM stock_price
  GROUP BY stock_id
),
first_close AS (
  SELECT b.stock_id, sp.close_usd AS first_close, b.first_asof
  FROM bounds b
  JOIN stock_price sp ON sp.stock_id = b.stock_id AND sp.asof = b.first_asof
),
last_close AS (
  SELECT b.stock_id, sp.close_usd AS last_close, b.last_asof
  FROM bounds b
  JOIN stock_price sp ON sp.stock_id = b.stock_id AND sp.asof = b.last_asof
),
current_assignment AS (
  -- For each stock, pick the assignment with the greatest effective_from
  -- that is on or before the latest observation date.
  SELECT
    lc.stock_id,
    (SELECT a.sector_id
       FROM stock_sector_assignment a
      WHERE a.stock_id = lc.stock_id
        AND a.effective_from <= lc.last_asof
      ORDER BY a.effective_from DESC
      LIMIT 1) AS sector_id
  FROM last_close lc
)
SELECT
  s.name,
  sec.level1                              AS sector_level1,
  sec.level2                              AS sector_level2,
  fc.first_asof,
  fc.first_close,
  lc.last_asof,
  lc.last_close,
  (lc.last_close - fc.first_close) / fc.first_close AS cumulative_return
FROM stock s
JOIN first_close          fc  ON fc.stock_id  = s.id
JOIN last_close           lc  ON lc.stock_id  = s.id
JOIN current_assignment   ca  ON ca.stock_id  = s.id
JOIN sector               sec ON sec.id       = ca.sector_id
ORDER BY cumulative_return DESC;
