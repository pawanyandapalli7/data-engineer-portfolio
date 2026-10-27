-- Latest version of each claim (the CDC snapshot pattern).
SELECT claim_id, member_id, claim_amount, claim_status, updated_at
FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY claim_id ORDER BY updated_at DESC) AS rn
    FROM claims
) t
WHERE rn = 1
ORDER BY claim_id;

-- Rank claims by amount within each member (ties share a rank).
SELECT member_id, claim_id, claim_amount,
       RANK() OVER (PARTITION BY member_id ORDER BY claim_amount DESC) AS amount_rank
FROM claims
ORDER BY member_id, amount_rank;

-- Running spend per member. ROWS (not the default RANGE) so two claims on the
-- same date accumulate one at a time; claim_id makes the order deterministic.
SELECT member_id, claim_date, claim_id, claim_amount,
       SUM(claim_amount) OVER (
           PARTITION BY member_id ORDER BY claim_date, claim_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_total
FROM claims
ORDER BY member_id, claim_date, claim_id;

-- Change versus the member's previous claim.
SELECT member_id, claim_date, claim_amount,
       claim_amount - LAG(claim_amount) OVER (PARTITION BY member_id ORDER BY claim_date, claim_id) AS change_from_prev
FROM claims
ORDER BY member_id, claim_date;
