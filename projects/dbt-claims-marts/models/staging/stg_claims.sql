select
    "Id"                                                        as claim_id,
    "PATIENTID"                                                 as patient_id,
    "PROVIDERID"                                                as provider_id,
    "PRIMARYPATIENTINSURANCEID"                                 as payer_id,
    try_cast(nullif(trim("SERVICEDATE"), '') as timestamptz)    as service_ts,
    nullif(trim("STATUS1"), '')                                 as status,
    try_cast(nullif(trim("OUTSTANDING1"), '') as decimal(12, 2)) as outstanding,
    nullif(trim("DIAGNOSIS1"), '')                              as primary_diagnosis
from {{ source('synthea', 'claims') }}
