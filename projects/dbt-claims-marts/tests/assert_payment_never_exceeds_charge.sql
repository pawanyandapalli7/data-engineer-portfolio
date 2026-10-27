-- A claim can't be paid more than it was charged.
select claim_id,
       sum(case when txn_type = 'CHARGE' then amount else 0 end)  as charged,
       sum(case when txn_type = 'PAYMENT' then amount else 0 end) as paid
from {{ ref('fct_claim_lines') }}
group by claim_id
having sum(case when txn_type = 'PAYMENT' then amount else 0 end)
     > sum(case when txn_type = 'CHARGE' then amount else 0 end)
