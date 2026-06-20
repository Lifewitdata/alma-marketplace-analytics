-- stg_providers.sql
-- Light cleaning + renaming of the raw providers table.
-- Grain: one row per provider.

with source as (

    select * from {{ source('raw', 'providers') }}

),

renamed as (

    select
        provider_id,
        provider_name,
        specialty                              as provider_specialty,
        state                                  as provider_state,
        cast(join_date as date)                as join_date,
        cast(churn_date as date)               as churn_date,
        status                                 as provider_status,
        accepts_insurance

    from source

)

select * from renamed
