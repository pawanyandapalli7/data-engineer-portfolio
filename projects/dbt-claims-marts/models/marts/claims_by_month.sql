select
    cast(date_trunc('month', service_date) as date)          as month,
    count(distinct claim_id)                                 as claims,
    sum(case when txn_type = 'CHARGE' then amount end)       as charged,
    sum(case when txn_type = 'PAYMENT' then amount end)      as paid
from {{ ref('fct_claim_lines') }}
group by 1
