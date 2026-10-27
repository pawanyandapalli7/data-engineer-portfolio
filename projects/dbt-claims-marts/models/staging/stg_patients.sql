-- Name and SSN columns in the source are not selected, so they never reach the warehouse.
select
    "Id"                                   as patient_id,
    try_cast(nullif(trim("BIRTHDATE"), '') as date) as birth_date,
    try_cast(nullif(trim("DEATHDATE"), '') as date) as death_date,
    nullif(trim("GENDER"), '')             as gender,
    nullif(trim("STATE"), '')              as state,
    nullif(trim("COUNTY"), '')             as county,
    nullif(trim("ZIP"), '')                as zip
from {{ source('synthea', 'patients') }}
