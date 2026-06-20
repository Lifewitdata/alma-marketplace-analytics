-- int_provider_session_rollup.sql
-- One row per provider, summarizing their session volume, claims performance,
-- and revenue contribution. Used as a building block for dim_providers and
-- the provider utilization mart.

with sessions as (

    select * from {{ ref('stg_sessions') }}

),

rollup as (

    select
        provider_id,
        count(*)                                                   as total_sessions,
        count(*) filter (where claim_status = 'approved')          as approved_sessions,
        count(*) filter (where claim_status = 'denied')             as denied_sessions,
        sum(billed_amount)                                          as total_billed,
        sum(reimbursed_amount)                                      as total_reimbursed,
        avg(days_to_pay)                                            as avg_days_to_pay,
        min(session_date)                                           as first_session_date,
        max(session_date)                                           as last_session_date

    from sessions
    group by provider_id

)

select
    *,
    case
        when total_sessions > 0
            then round(approved_sessions::numeric / total_sessions, 4)
        else null
    end as claim_approval_rate
from rollup
