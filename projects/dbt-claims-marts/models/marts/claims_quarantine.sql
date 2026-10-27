-- Rows that fail a business rule are kept here with every rule they broke,
-- instead of being dropped. The marts below read only rows absent from here.
with checks as (
    select 'patient' as entity, patient_id as record_id,
        [x for x in [
            case when birth_date is null or birth_date > current_date then 'birth_date_valid' end,
            case when gender not in ('M', 'F') or gender is null then 'gender_known' end
        ] if x is not null] as failed_checks
    from {{ ref('stg_patients') }}

    union all

    select 'claim', claim_id,
        [x for x in [
            case when patient_id is null then 'patient_linked' end,
            case when service_ts is null then 'service_date_present' end,
            case when outstanding < 0 then 'outstanding_not_negative' end
        ] if x is not null]
    from {{ ref('stg_claims') }}
)
select entity, record_id, failed_checks
from checks
where len(failed_checks) > 0
