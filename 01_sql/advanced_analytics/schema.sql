-- Claims table used for analytics and SQL examples
CREATE TABLE claims (
    claim_id        BIGINT,
    member_id       BIGINT,
    provider_id     BIGINT,
    claim_amount    DECIMAL(10,2),
    claim_status    VARCHAR(20),
    claim_date      DATE,
    updated_at      TIMESTAMP
);
