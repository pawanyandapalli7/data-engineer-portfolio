-- Monthly spend per member
SELECT
    member_id,
    DATE_TRUNC('month', claim_date) AS month,
    SUM(claim_amount) AS total_spend
FROM claims
GROUP BY member_id, month;

-- Top 5 members by total spend
SELECT
    member_id,
    SUM(claim_amount) AS total_spend
FROM claims
GROUP BY member_id
ORDER BY total_spend DESC
LIMIT 5;

-- Claim approval rate
SELECT
    100.0 * COUNT(*) FILTER (WHERE claim_status = 'APPROVED')
    / COUNT(*) AS approval_rate
FROM claims;
