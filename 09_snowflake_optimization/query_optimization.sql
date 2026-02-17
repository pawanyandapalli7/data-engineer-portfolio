-- Avoid SELECT *
SELECT
    claim_date,
    SUM(amount) AS total_amount
FROM fact_claims
WHERE claim_date >= '2024-01-01'
GROUP BY claim_date;
