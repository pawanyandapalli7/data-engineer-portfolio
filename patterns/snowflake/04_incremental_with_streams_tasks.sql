-- Incremental processing inside Snowflake: a stream tracks new rows in the raw
-- table and a task merges them every 15 minutes, only when there is data.
CREATE OR REPLACE STREAM raw.claims_changes ON TABLE raw.claims;

CREATE OR REPLACE TASK curated.merge_claims
  WAREHOUSE = wh_ingest
  SCHEDULE = '15 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('raw.claims_changes')   -- skips the run (and the credits) when idle
AS
MERGE INTO curated.claims t
USING (
    SELECT *
    FROM raw.claims_changes
    WHERE METADATA$ACTION = 'INSERT'
    QUALIFY ROW_NUMBER() OVER (PARTITION BY claim_id ORDER BY updated_at DESC) = 1
) s
ON t.claim_id = s.claim_id
WHEN MATCHED AND s.updated_at > t.updated_at THEN UPDATE SET
    member_id = s.member_id, claim_amount = s.claim_amount, claim_status = s.claim_status,
    claim_date = s.claim_date, updated_at = s.updated_at
WHEN NOT MATCHED THEN INSERT (claim_id, member_id, claim_amount, claim_status, claim_date, updated_at)
    VALUES (s.claim_id, s.member_id, s.claim_amount, s.claim_status, s.claim_date, s.updated_at);

ALTER TASK curated.merge_claims RESUME;
