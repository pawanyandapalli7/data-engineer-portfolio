-- Snowflake: offline event log written by OfflineFeatureWriter (append-only).
CREATE TABLE IF NOT EXISTS user_features (
    event_id              STRING        NOT NULL,   -- duplicates possible (at-least-once); deduped on read
    user_id               STRING        NOT NULL,
    event_type            STRING,
    event_ts              NUMBER(38, 0) NOT NULL,   -- epoch seconds, same clock the online store uses
    session_duration_sec  NUMBER,
    items_viewed          NUMBER,
    cart_value_usd        NUMBER(12, 2),
    is_mobile             NUMBER(1),
    written_at            TIMESTAMP_NTZ
);

-- Training labels: one row per (user, moment we need a prediction for).
CREATE TABLE IF NOT EXISTS labels (
    user_id   STRING        NOT NULL,
    label_ts  NUMBER(38, 0) NOT NULL,   -- epoch seconds
    is_fraud  BOOLEAN       NOT NULL
);
