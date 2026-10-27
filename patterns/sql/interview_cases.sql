-- Members whose claim amount went up at least once, claim over claim.
-- Ties on claim_date are ordered by claim_id so the result is deterministic.
SELECT DISTINCT member_id
FROM (
    SELECT member_id,
           claim_amount,
           LAG(claim_amount) OVER (PARTITION BY member_id ORDER BY claim_date, claim_id) AS prev_amount
    FROM claims
) t
WHERE claim_amount > prev_amount
ORDER BY member_id;

-- Members whose claims rose every single time (strictly increasing, 2+ claims).
SELECT member_id
FROM (
    SELECT member_id,
           claim_amount - LAG(claim_amount) OVER (PARTITION BY member_id ORDER BY claim_date, claim_id) AS delta
    FROM claims
) t
GROUP BY member_id
HAVING COUNT(delta) >= 1 AND MIN(delta) > 0
ORDER BY member_id;

-- Spike detection: a claim more than 3x the member's average of their OTHER
-- claims. Including the claim itself in the average would hide the spike.
SELECT member_id, claim_id, claim_date, claim_amount, avg_other_claims
FROM (
    SELECT member_id, claim_id, claim_date, claim_amount,
           (SUM(claim_amount) OVER w - claim_amount) / NULLIF(COUNT(*) OVER w - 1, 0) AS avg_other_claims
    FROM claims
    WINDOW w AS (PARTITION BY member_id)
) t
WHERE claim_amount > 3 * avg_other_claims
ORDER BY member_id, claim_date;
