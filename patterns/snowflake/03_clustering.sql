-- Clustering keys pay off on large tables (roughly multi-TB) that are filtered on
-- the same columns again and again. Check before and after instead of assuming.

-- 1. How well does the table prune on claim_date today?
SELECT SYSTEM$CLUSTERING_INFORMATION('analytics.fact_claims', '(claim_date)');
--    Look at average_depth: close to 1 = well clustered; large = every query scans many micro-partitions.

-- 2. Only if depth is poor AND the filter is common: add a key.
--    Low-cardinality first, and wrap timestamps in a coarser expression.
ALTER TABLE analytics.fact_claims CLUSTER BY (claim_date, payer_id);

-- 3. Automatic clustering costs credits. Watch it.
SELECT DATE_TRUNC(day, start_time) AS day, ROUND(SUM(credits_used), 2) AS reclustering_credits
FROM snowflake.account_usage.automatic_clustering_history
WHERE table_name = 'FACT_CLAIMS' AND start_time >= DATEADD(day, -14, CURRENT_TIMESTAMP())
GROUP BY 1 ORDER BY 1;
