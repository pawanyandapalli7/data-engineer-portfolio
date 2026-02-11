-- Purpose:
-- Time-based aggregation used for monthly analytics reporting
-- and spend trend analysis per member
SELECT
    member_id,
    DATE_TRUNC('month', claim_date) AS month,
    SUM(claim_amount) AS total_spend
FROM claims
GROUP BY
    member_id,
    DATE_TRUNC('month', claim_date);

-- Purpose:
-- Identify high-value members based on total claim spend
-- Commonly used for cost analysis and risk segmentation
SELECT
    member_id,
    SUM(claim_amount) AS total_spend
FROM claims
GROUP BY member_id
ORDER BY total_spend DESC
LIMIT 5;

-- Purpose:
-- Compute approval rate KPI for claims processing performance
-- Uses FILTER for concise conditional aggregation
SELECT
    100.0 * COUNT(*) FILTER (WHERE claim_status = 'APPROVED')
    / COUNT(*) AS approval_rate
FROM claims;
