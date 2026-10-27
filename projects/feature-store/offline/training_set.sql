-- Point-in-time training set.
--
-- For every label, features are computed only from events at or before the
-- label's timestamp, so no row can see the future. The velocity windows use the
-- same boundaries as velocity_features() in src/ingestion/consumer.py
-- (ts <= now AND ts > now - window), which tests/test_feature_store.py checks
-- row-for-row against the online path.
--
-- Runs as-is on Snowflake and on DuckDB (used by the tests).
WITH events AS (
    SELECT *
    FROM user_features
    QUALIFY ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY written_at) = 1   -- drop replayed duplicates
),
latest_event AS (
    SELECT l.user_id, l.label_ts, l.is_fraud,
           e.event_ts AS last_event_ts, e.event_type, e.cart_value_usd, e.is_mobile
    FROM labels l
    LEFT JOIN events e
      ON e.user_id = l.user_id
     AND e.event_ts <= l.label_ts
    QUALIFY ROW_NUMBER() OVER (PARTITION BY l.user_id, l.label_ts ORDER BY e.event_ts DESC NULLS LAST) = 1
),
velocity AS (
    SELECT l.user_id, l.label_ts,
           SUM(CASE WHEN e.event_ts > l.label_ts - 3600 THEN 1 ELSE 0 END) AS event_count_1h,
           COUNT(e.event_id)                                              AS event_count_24h,
           COALESCE(SUM(e.cart_value_usd), 0)                             AS cart_value_sum_24h,
           COALESCE(MAX(e.cart_value_usd), 0)                             AS cart_value_max_24h
    FROM labels l
    LEFT JOIN events e
      ON e.user_id = l.user_id
     AND e.event_ts <= l.label_ts
     AND e.event_ts >  l.label_ts - 86400
    GROUP BY l.user_id, l.label_ts
)
SELECT le.user_id, le.label_ts, le.is_fraud,
       le.last_event_ts, le.event_type, le.cart_value_usd, le.is_mobile,
       v.event_count_1h, v.event_count_24h, v.cart_value_sum_24h, v.cart_value_max_24h
FROM latest_event le
JOIN velocity v USING (user_id, label_ts)
ORDER BY le.user_id, le.label_ts
