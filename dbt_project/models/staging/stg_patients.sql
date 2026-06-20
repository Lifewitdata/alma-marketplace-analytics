-- stg_patients.sql
-- Light cleaning + renaming of the raw patients table.
-- Grain: one row per patient.

with source as (

    select * from {{ source('raw', 'patients') }}

),

renamed as (

    select
        patient_id,
        cast(signup_date as date)              as signup_date,
        state                                  as patient_state,
        specialty_needed,
        payer_id

    from source

)

select * from renamed
