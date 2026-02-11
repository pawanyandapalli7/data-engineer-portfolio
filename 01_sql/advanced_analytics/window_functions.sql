-- Deduplicate records (latest per claim)
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

-- Rank claims by amount per member
SELECT
    member_id,
    claim_id,
    claim_amount,
    RANK() OVER (
        PARTITION BY member_id
        ORDER BY claim_amount DESC
    ) AS amount_rank
FROM claims;

-- Running total of claims per member
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

-- Compare current vs previous claim
SELECT
    member_id,
    claim_date,
    claim_amount,
    LAG(claim_amount) OVER (
        PARTITION BY member_id
        ORDER BY claim_date
    ) AS previous_claim_amount
FROM claims;
