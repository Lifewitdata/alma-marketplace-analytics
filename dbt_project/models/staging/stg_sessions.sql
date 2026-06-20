-- stg_sessions.sql
-- Light cleaning + renaming of the raw sessions (claims) table.
-- Grain: one row per therapy session / billable claim.

with source as (

    select * from {{ source('raw', 'sessions') }}

),

renamed as (

    select
        session_id,
        match_id,
        patient_id,
        provider_id,
        payer_id,
        cast(session_date as date)             as session_date,
        billed_amount,
        claim_status,
        denial_reason,
        days_to_pay,
        reimbursed_amount

    from source

)

select * from renamed
