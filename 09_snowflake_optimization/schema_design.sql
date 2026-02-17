-- Fact table optimized for analytics
CREATE OR REPLACE TABLE fact_claims (
    claim_id STRING,
    member_id STRING,
    provider_id STRING,
    claim_date DATE,
    amount NUMBER(10,2)
);
