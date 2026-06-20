-- fct_matches.sql
-- Match-level fact table. Grain: one row per match attempt.
-- Primary table for the "time-to-match by specialty" dashboard.

with matches as (

    select * from {{ ref('int_time_to_match') }}

)

select
    match_id,
    patient_id,
    provider_id,
    match_specialty,
    match_date,
    time_to_match_days,
    time_to_match_bucket,
    match_outcome,
    patient_state,
    provider_state,
    signup_date,

    -- flags for easy aggregation in BI tools
    case when match_outcome = 'accepted' then 1 else 0 end as is_accepted,
    case when match_outcome != 'accepted' then 1 else 0 end as is_declined,
    case when patient_state = provider_state then 1 else 0 end as is_same_state_match

from matches
