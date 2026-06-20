-- fct_sessions.sql
-- Session-level fact table (= billable claims). Grain: one row per session.
-- Primary table for claims approval rate, revenue, and reimbursement-lag analysis.

with sessions as (

    select * from {{ ref('stg_sessions') }}

),

payers as (

    select * from {{ ref('stg_payers') }}

),

final as (

    select
        s.session_id,
        s.match_id,
        s.patient_id,
        s.provider_id,
        s.payer_id,
        pa.payer_name,
        s.session_date,
        s.billed_amount,
        s.claim_status,
        s.denial_reason,
        s.days_to_pay,
        s.reimbursed_amount,

        -- net revenue leakage on this session (what Alma/provider didn't collect)
        case
            when s.claim_status = 'denied' then s.billed_amount
            else s.billed_amount - coalesce(s.reimbursed_amount, 0)
        end as revenue_leakage,

        case when s.claim_status = 'approved' then 1 else 0 end as is_approved,
        case when s.claim_status = 'denied' then 1 else 0 end as is_denied

    from sessions s
    left join payers pa on s.payer_id = pa.payer_id

)

select * from final
