-- Purpose:
-- Identify members whose claim amounts show an increasing pattern over time.
-- Commonly used for trend analysis and anomaly detection in claims data.
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

-- Purpose:
-- Detect potential fraud or abnormal spikes by comparing individual claims
-- against a member's historical average claim amount.
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
