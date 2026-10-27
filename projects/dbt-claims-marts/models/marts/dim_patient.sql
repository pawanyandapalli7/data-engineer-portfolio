-- One row per patient version (SCD Type 2), from the dbt snapshot.
select
    patient_id,
    gender,
    state,
    county,
    zip,
    death_date,
    dbt_valid_from                                   as valid_from,
    dbt_valid_to                                     as valid_to,
    dbt_valid_to = cast('9999-12-31' as timestamp)   as is_current
from {{ ref('patients_snapshot') }}
where patient_id not in (
    select record_id from {{ ref('claims_quarantine') }} where entity = 'patient'
)
