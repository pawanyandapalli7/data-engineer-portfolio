-- Purpose:
-- Deduplicate records by retaining the latest version per claim.
-- Commonly used in CDC pipelines and snapshot generation.
SELECT *
FROM (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY claim_id
               ORDER BY updated_at DESC
           ) AS rn
    FROM claims
) t
WHERE rn = 1;

-- Purpose:
-- Rank claims by amount within each member.
-- Used for cost analysis and outlier detection.
SELECT
    member_id,
    claim_id,
    claim_amount,
    RANK() OVER (
        PARTITION BY member_id
        ORDER BY claim_amount DESC
    ) AS amount_rank
FROM claims;

-- Purpose:
-- Compute cumulative claim spend over time per member.
-- Commonly used for trend analysis and reporting.
SELECT
    member_id,
    claim_date,
    claim_amount,
    SUM(claim_amount) OVER (
        PARTITION BY member_id
        ORDER BY claim_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM claims;

-- Purpose:
-- Compare current claim amounts with previous claims.
-- Used to analyze changes and detect abnormal increases.
SELECT
    member_id,
    claim_date,
    claim_amount,
    LAG(claim_amount) OVER (
        PARTITION BY member_id
        ORDER BY claim_date
    ) AS previous_claim_amount
FROM claims;
