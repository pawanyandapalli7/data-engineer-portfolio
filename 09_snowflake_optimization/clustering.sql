-- Improve pruning on commonly filtered columns
ALTER TABLE fact_claims
CLUSTER BY (claim_date);
