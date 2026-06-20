-- stg_payers.sql
-- Light cleaning + renaming of the raw payers reference table.
-- Grain: one row per payer.

with source as (

    select * from {{ source('raw', 'payers') }}

),

renamed as (

    select
        payer_id,
        payer_name,
        base_approval_rate,
        base_days_to_pay

    from source

)

select * from renamed
