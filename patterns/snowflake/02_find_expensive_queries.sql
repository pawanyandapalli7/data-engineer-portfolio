-- Where the time goes: the slowest query shapes of the last 7 days, and whether
-- they prune or spill. Run with a role that can read SNOWFLAKE.ACCOUNT_USAGE
-- (data there lags by up to ~45 minutes).
SELECT
    query_parameterized_hash,
    ANY_VALUE(LEFT(query_text, 200))                               AS sample_query,
    warehouse_name,
    COUNT(*)                                                       AS runs,
    ROUND(SUM(total_elapsed_time) / 1000 / 60, 1)                  AS total_minutes,
    ROUND(AVG(partitions_scanned / NULLIF(partitions_total, 0)), 3) AS avg_fraction_scanned,  -- near 1.0 = no pruning
    SUM(bytes_spilled_to_local_storage)  > 0                       AS spills_local,
    SUM(bytes_spilled_to_remote_storage) > 0                       AS spills_remote          -- warehouse too small
FROM snowflake.account_usage.query_history
WHERE start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
  AND execution_status = 'SUCCESS'
GROUP BY query_parameterized_hash, warehouse_name
ORDER BY total_minutes DESC
LIMIT 20;

-- Credits by warehouse per day, to see what the guardrails are protecting.
SELECT warehouse_name, DATE_TRUNC(day, start_time) AS day, ROUND(SUM(credits_used), 2) AS credits
FROM snowflake.account_usage.warehouse_metering_history
WHERE start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
GROUP BY 1, 2
ORDER BY day DESC, credits DESC;
