-- dim_specialty_supply_demand.sql
-- Specialty-level supply vs. demand summary. This is the table that powers
-- the headline insight: which specialties are under-supplied relative to
-- patient demand, evidenced by longer time-to-match and higher decline rates.

with active_providers as (

    select
        provider_specialty,
        count(*) as active_provider_count
    from {{ ref('dim_providers') }}
    where provider_status = 'active'
    group by provider_specialty

),

match_stats as (

    select
        match_specialty,
        count(*)                                                   as total_matches,
        round(avg(time_to_match_days), 2)                          as avg_time_to_match_days,
        round(
            sum(is_declined)::numeric / nullif(count(*), 0), 4
        )                                                          as decline_rate
    from {{ ref('fct_matches') }}
    group by match_specialty

)

select
    m.match_specialty                                              as specialty,
    m.total_matches                                                as patient_demand,
    coalesce(p.active_provider_count, 0)                           as active_providers,
    m.avg_time_to_match_days,
    m.decline_rate,
    round(
        m.total_matches::numeric / nullif(p.active_provider_count, 0), 2
    )                                                              as patients_per_provider

from match_stats m
left join active_providers p on m.match_specialty = p.provider_specialty
order by m.avg_time_to_match_days desc
