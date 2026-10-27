select
    "ID"                                                      as transaction_id,
    "CLAIMID"                                                 as claim_id,
    "PATIENTID"                                               as patient_id,
    upper(nullif(trim("TYPE"), ''))                           as txn_type,
    try_cast(nullif(trim("AMOUNT"), '') as decimal(12, 2))    as amount,
    try_cast(nullif(trim("FROMDATE"), '') as timestamptz)     as from_ts,
    nullif(trim("PROCEDURECODE"), '')                         as procedure_code
from {{ source('synthea', 'claims_transactions') }}
