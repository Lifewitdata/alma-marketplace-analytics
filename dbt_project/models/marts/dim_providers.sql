-- dim_providers.sql
-- Provider dimension table. One row per provider, with status, specialty,
-- and rolled-up performance metrics. This is the table BI tools join to.

with providers as (

    select * from {{ ref('stg_providers') }}

),

rollup as (

    select * from {{ ref('int_provider_session_rollup') }}

),

final as (

    select
        p.provider_id,
        p.provider_name,
        p.provider_specialty,
        p.provider_state,
        p.join_date,
        p.churn_date,
        p.provider_status,
        p.accepts_insurance,

        coalesce(r.total_sessions, 0)           as total_sessions,
        coalesce(r.approved_sessions, 0)        as approved_sessions,
        coalesce(r.denied_sessions, 0)          as denied_sessions,
        r.claim_approval_rate,
        coalesce(r.total_billed, 0)             as total_billed,
        coalesce(r.total_reimbursed, 0)         as total_reimbursed,
        r.avg_days_to_pay,
        r.first_session_date,
        r.last_session_date,

        -- tenure in days (to churn date if churned, else to today's proxy = last_session_date)
        case
            when p.provider_status = 'churned'
                then p.churn_date - p.join_date
            else null
        end as days_active_before_churn

    from providers p
    left join rollup r on p.provider_id = r.provider_id

)

select * from final
