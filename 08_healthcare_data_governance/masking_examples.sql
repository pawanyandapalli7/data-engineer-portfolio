-- Mask PHI fields for non-privileged roles
CREATE OR REPLACE VIEW masked_claims AS
SELECT
    claim_id,
    member_id,
    '***MASKED***' AS ssn,
    claim_date,
    amount
FROM fact_claims;
