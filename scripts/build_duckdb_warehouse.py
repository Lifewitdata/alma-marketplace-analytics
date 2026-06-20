"""
build_duckdb_warehouse.py
--------------------------
Builds a local DuckDB warehouse that mirrors the dbt project's DAG:

    raw  ->  staging  ->  intermediate  ->  marts

This lets anyone clone the repo and get a working, queryable warehouse
with zero external dependencies (no Snowflake/BigQuery account needed) -
just `pip install duckdb` and run this script. The SQL here is a direct,
non-Jinja translation of the .sql files in dbt_project/models/, so the
two should always be kept in sync.

In a real production setting, this same project would point dbt at the
company's actual warehouse (Snowflake/BigQuery/Postgres) using a
profiles.yml - DuckDB is used here purely so the project is runnable
end-to-end as a portfolio piece.

Run:
    python scripts/build_duckdb_warehouse.py
"""

import os

import duckdb

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "processed", "alma_dev.duckdb")
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")


def load_raw_tables(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
    for tbl in ["providers", "patients", "payers", "matches", "sessions"]:
        path = os.path.join(RAW_DIR, f"{tbl}.csv").replace("\\", "/")
        con.execute(f"""
            CREATE OR REPLACE TABLE raw.{tbl} AS
            SELECT * FROM read_csv_auto('{path}');
        """)


def build_staging(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS staging;")

    con.execute("""
        CREATE OR REPLACE TABLE staging.stg_providers AS
        SELECT
            provider_id,
            provider_name,
            specialty AS provider_specialty,
            state AS provider_state,
            CAST(join_date AS DATE) AS join_date,
            CAST(churn_date AS DATE) AS churn_date,
            status AS provider_status,
            accepts_insurance
        FROM raw.providers;
    """)

    con.execute("""
        CREATE OR REPLACE TABLE staging.stg_patients AS
        SELECT
            patient_id,
            CAST(signup_date AS DATE) AS signup_date,
            state AS patient_state,
            specialty_needed,
            payer_id
        FROM raw.patients;
    """)

    con.execute("""
        CREATE OR REPLACE TABLE staging.stg_payers AS
        SELECT payer_id, payer_name, base_approval_rate, base_days_to_pay
        FROM raw.payers;
    """)

    con.execute("""
        CREATE OR REPLACE TABLE staging.stg_matches AS
        SELECT
            match_id,
            patient_id,
            provider_id,
            specialty AS match_specialty,
            CAST(match_date AS DATE) AS match_date,
            time_to_match_days,
            outcome AS match_outcome
        FROM raw.matches;
    """)

    con.execute("""
        CREATE OR REPLACE TABLE staging.stg_sessions AS
        SELECT
            session_id, match_id, patient_id, provider_id, payer_id,
            CAST(session_date AS DATE) AS session_date,
            billed_amount, claim_status, denial_reason, days_to_pay, reimbursed_amount
        FROM raw.sessions;
    """)


def build_intermediate(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS intermediate;")

    con.execute("""
        CREATE OR REPLACE TABLE intermediate.int_provider_session_rollup AS
        WITH rollup AS (
            SELECT
                provider_id,
                COUNT(*) AS total_sessions,
                COUNT(*) FILTER (WHERE claim_status = 'approved') AS approved_sessions,
                COUNT(*) FILTER (WHERE claim_status = 'denied') AS denied_sessions,
                SUM(billed_amount) AS total_billed,
                SUM(reimbursed_amount) AS total_reimbursed,
                AVG(days_to_pay) AS avg_days_to_pay,
                MIN(session_date) AS first_session_date,
                MAX(session_date) AS last_session_date
            FROM staging.stg_sessions
            GROUP BY provider_id
        )
        SELECT
            *,
            CASE WHEN total_sessions > 0
                 THEN ROUND(approved_sessions::DOUBLE / total_sessions, 4)
                 ELSE NULL END AS claim_approval_rate
        FROM rollup;
    """)

    con.execute("""
        CREATE OR REPLACE TABLE intermediate.int_time_to_match AS
        SELECT
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
            CASE
                WHEN m.time_to_match_days <= 2 THEN '0-2 days'
                WHEN m.time_to_match_days <= 5 THEN '3-5 days'
                WHEN m.time_to_match_days <= 10 THEN '6-10 days'
                ELSE '10+ days'
            END AS time_to_match_bucket
        FROM staging.stg_matches m
        LEFT JOIN staging.stg_patients p ON m.patient_id = p.patient_id
        LEFT JOIN staging.stg_providers pr ON m.provider_id = pr.provider_id;
    """)


def build_marts(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS marts;")

    con.execute("""
        CREATE OR REPLACE TABLE marts.dim_providers AS
        SELECT
            p.provider_id, p.provider_name, p.provider_specialty, p.provider_state,
            p.join_date, p.churn_date, p.provider_status, p.accepts_insurance,
            COALESCE(r.total_sessions, 0) AS total_sessions,
            COALESCE(r.approved_sessions, 0) AS approved_sessions,
            COALESCE(r.denied_sessions, 0) AS denied_sessions,
            r.claim_approval_rate,
            COALESCE(r.total_billed, 0) AS total_billed,
            COALESCE(r.total_reimbursed, 0) AS total_reimbursed,
            r.avg_days_to_pay,
            r.first_session_date,
            r.last_session_date,
            CASE WHEN p.provider_status = 'churned'
                 THEN p.churn_date - p.join_date ELSE NULL END AS days_active_before_churn
        FROM staging.stg_providers p
        LEFT JOIN intermediate.int_provider_session_rollup r ON p.provider_id = r.provider_id;
    """)

    con.execute("""
        CREATE OR REPLACE TABLE marts.fct_matches AS
        SELECT
            match_id, patient_id, provider_id, match_specialty, match_date,
            time_to_match_days, time_to_match_bucket, match_outcome,
            patient_state, provider_state, signup_date,
            CASE WHEN match_outcome = 'accepted' THEN 1 ELSE 0 END AS is_accepted,
            CASE WHEN match_outcome != 'accepted' THEN 1 ELSE 0 END AS is_declined,
            CASE WHEN patient_state = provider_state THEN 1 ELSE 0 END AS is_same_state_match
        FROM intermediate.int_time_to_match;
    """)

    con.execute("""
        CREATE OR REPLACE TABLE marts.fct_sessions AS
        SELECT
            s.session_id, s.match_id, s.patient_id, s.provider_id, s.payer_id, pa.payer_name,
            s.session_date, s.billed_amount, s.claim_status, s.denial_reason,
            s.days_to_pay, s.reimbursed_amount,
            CASE WHEN s.claim_status = 'denied' THEN s.billed_amount
                 ELSE s.billed_amount - COALESCE(s.reimbursed_amount, 0) END AS revenue_leakage,
            CASE WHEN s.claim_status = 'approved' THEN 1 ELSE 0 END AS is_approved,
            CASE WHEN s.claim_status = 'denied' THEN 1 ELSE 0 END AS is_denied
        FROM staging.stg_sessions s
        LEFT JOIN staging.stg_payers pa ON s.payer_id = pa.payer_id;
    """)

    con.execute("""
        CREATE OR REPLACE TABLE marts.dim_specialty_supply_demand AS
        WITH active_providers AS (
            SELECT provider_specialty, COUNT(*) AS active_provider_count
            FROM marts.dim_providers
            WHERE provider_status = 'active'
            GROUP BY provider_specialty
        ),
        match_stats AS (
            SELECT
                match_specialty,
                COUNT(*) AS total_matches,
                ROUND(AVG(time_to_match_days), 2) AS avg_time_to_match_days,
                ROUND(SUM(is_declined)::DOUBLE / NULLIF(COUNT(*), 0), 4) AS decline_rate
            FROM marts.fct_matches
            GROUP BY match_specialty
        )
        SELECT
            m.match_specialty AS specialty,
            m.total_matches AS patient_demand,
            COALESCE(p.active_provider_count, 0) AS active_providers,
            m.avg_time_to_match_days,
            m.decline_rate,
            ROUND(m.total_matches::DOUBLE / NULLIF(p.active_provider_count, 0), 2) AS patients_per_provider
        FROM match_stats m
        LEFT JOIN active_providers p ON m.match_specialty = p.provider_specialty
        ORDER BY m.avg_time_to_match_days DESC;
    """)


def run_tests(con: duckdb.DuckDBPyConnection) -> None:
    """Minimal stand-ins for the dbt schema tests (uniqueness, not-null, accepted values)."""
    checks = [
        ("dim_providers PK unique", """
            SELECT COUNT(*) FROM (
                SELECT provider_id FROM marts.dim_providers
                GROUP BY provider_id HAVING COUNT(*) > 1
            )
        """),
        ("fct_matches PK unique", """
            SELECT COUNT(*) FROM (
                SELECT match_id FROM marts.fct_matches
                GROUP BY match_id HAVING COUNT(*) > 1
            )
        """),
        ("fct_sessions PK unique", """
            SELECT COUNT(*) FROM (
                SELECT session_id FROM marts.fct_sessions
                GROUP BY session_id HAVING COUNT(*) > 1
            )
        """),
        ("fct_matches no null match_outcome", """
            SELECT COUNT(*) FROM marts.fct_matches WHERE match_outcome IS NULL
        """),
    ]
    print("\nRunning data quality checks...")
    all_passed = True
    for name, query in checks:
        result = con.execute(query).fetchone()[0]
        status = "PASS" if result == 0 else "FAIL"
        if result != 0:
            all_passed = False
        print(f"  [{status}] {name} (violations: {result})")
    if all_passed:
        print("All checks passed.\n")
    else:
        print("Some checks failed - investigate before trusting downstream marts.\n")


def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = duckdb.connect(DB_PATH)

    print("Loading raw tables...")
    load_raw_tables(con)

    print("Building staging layer...")
    build_staging(con)

    print("Building intermediate layer...")
    build_intermediate(con)

    print("Building marts layer...")
    build_marts(con)

    run_tests(con)

    print("Warehouse build complete ->", DB_PATH)
    con.close()


if __name__ == "__main__":
    main()
