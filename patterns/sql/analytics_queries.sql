-- Monthly spend per member.
SELECT member_id, DATE_TRUNC('month', claim_date) AS month, SUM(claim_amount) AS total_spend
FROM claims
GROUP BY member_id, DATE_TRUNC('month', claim_date)
ORDER BY member_id, month;

-- Top 5 members by spend (ties broken by member_id so the cut-off is stable).
SELECT member_id, SUM(claim_amount) AS total_spend
FROM claims
GROUP BY member_id
ORDER BY total_spend DESC, member_id
LIMIT 5;

-- Approval rate. FILTER is PostgreSQL / DuckDB; in Snowflake use COUNT_IF(claim_status = 'APPROVED').
SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE claim_status = 'APPROVED') / NULLIF(COUNT(*), 0), 2) AS approval_rate_pct
FROM claims;
