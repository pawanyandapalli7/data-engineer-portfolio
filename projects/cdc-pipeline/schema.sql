-- Source table in PostgreSQL (what DMS replicates).
CREATE TABLE claims (
    claim_id      VARCHAR(36) PRIMARY KEY,
    member_id     VARCHAR(36) NOT NULL,
    claim_amount  NUMERIC(12, 2),
    claim_date    DATE,
    status        VARCHAR(20),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Shape of the raw CDC files DMS lands in S3 (one row per change).
-- op         : I / U / D  (NULL for full-load rows unless includeOpForFullLoad = true)
-- event_ts   : source commit timestamp (DMS transaction timestamp)
-- change_seq : DMS change sequence, used to order changes inside one commit
--
-- claim_id | member_id | claim_amount | claim_date | status | updated_at | op | event_ts | change_seq
