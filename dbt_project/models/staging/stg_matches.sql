-- stg_matches.sql
-- Light cleaning + renaming of the raw matches table.
-- Grain: one row per patient-provider match attempt.

with source as (

    select * from {{ source('raw', 'matches') }}

),

renamed as (

    select
        match_id,
        patient_id,
        provider_id,
        specialty                              as match_specialty,
        cast(match_date as date)               as match_date,
        time_to_match_days,
        outcome                                as match_outcome

    from source

)

select * from renamed
