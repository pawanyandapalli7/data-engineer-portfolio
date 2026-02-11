-- Find members with increasing claim amounts
SELECT DISTINCT member_id
FROM (
    SELECT
        member_id,
        claim_amount,
        LAG(claim_amount) OVER (
            PARTITION BY member_id
            ORDER BY claim_date
        ) AS prev_amount
    FROM claims
) t
WHERE claim_amount > prev_amount;

-- Detect potential fraud (spike detection)
SELECT *
FROM (
    SELECT
        member_id,
        claim_date,
        claim_amount,
        AVG(claim_amount) OVER (
            PARTITION BY member_id
        ) AS avg_amount
    FROM claims
) t
WHERE claim_amount > avg_amount * 3;
