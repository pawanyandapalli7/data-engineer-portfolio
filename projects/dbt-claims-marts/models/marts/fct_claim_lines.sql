{{ config(
    materialized='incremental',
    unique_key='transaction_id',
    incremental_strategy='delete+insert',
    on_schema_change='fail'
) }}

-- One row per claim transaction. Incremental: a re-run only reprocesses
-- transactions on or after the latest service date already loaded.
select
    t.transaction_id,
    t.claim_id,
    t.patient_id,
    c.provider_id,
    c.payer_id,
    cast(c.service_ts as date) as service_date,
    t.txn_type,
    t.amount,
    t.procedure_code,
    c.primary_diagnosis
from {{ ref('stg_claim_transactions') }} t
join {{ ref('stg_claims') }} c using (claim_id)
where c.claim_id not in (
    select record_id from {{ ref('claims_quarantine') }} where entity = 'claim'
)
{% if is_incremental() %}
  and cast(c.service_ts as date) >= (select max(service_date) from {{ this }})
{% endif %}
