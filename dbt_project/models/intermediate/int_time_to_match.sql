-- int_time_to_match.sql
-- Match-level model enriched with patient and provider attributes.
-- This is the base for the core "supply gap" insight: which specialties
-- have the longest time-to-match, and where outcomes are worst.

with matches as (

    select * from {{ ref('stg_matches') }}

),

patients as (

    select * from {{ ref('stg_patients') }}

),

providers as (

    select * from {{ ref('stg_providers') }}

),

joined as (

    select
        m.match_id,
        m.patient_id,
        m.provider_id,
        m.match_specialty,
        m.match_date,
        m.time_to_match_days,
        m.match_outcome,
        p.patient_state,
        p.signup_date,
        pr.provider_state,
        pr.provider_status,

        -- bucket time-to-match for easier dashboard filtering
        case
            when m.time_to_match_days <= 2 then '0-2 days'
            when m.time_to_match_days <= 5 then '3-5 days'
            when m.time_to_match_days <= 10 then '6-10 days'
            else '10+ days'
        end as time_to_match_bucket

    from matches m
    left join patients p on m.patient_id = p.patient_id
    left join providers pr on m.provider_id = pr.provider_id

)

select * from joined
