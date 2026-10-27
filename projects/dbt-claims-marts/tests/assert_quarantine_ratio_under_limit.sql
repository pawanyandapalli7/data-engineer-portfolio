-- Fail the build if more than max_quarantine_ratio of claims are quarantined,
-- the same circuit breaker the Databricks job applies.
with q as (select count(*) as bad from {{ ref('claims_quarantine') }} where entity = 'claim'),
     t as (select count(*) as total from {{ ref('stg_claims') }})
select bad, total, bad * 1.0 / total as ratio
from q, t
where bad * 1.0 / nullif(total, 0) > {{ var('max_quarantine_ratio') }}
