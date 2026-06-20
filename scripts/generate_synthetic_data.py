"""
generate_synthetic_data.py
---------------------------
Generates a synthetic dataset that mimics Alma's core marketplace data:
providers, patients, payers, matches, and sessions.

This is NOT real Alma data. It's a realistic simulation built to demonstrate
end-to-end data modeling and analytics skills (raw source tables -> dbt
staging/marts -> BI dashboard) for a Data Analyst portfolio project.

Run:
    python scripts/generate_synthetic_data.py

Outputs CSVs to data/raw/:
    providers.csv
    patients.csv
    payers.csv
    matches.csv
    sessions.csv
"""

import random
from datetime import date, timedelta

import numpy as np
import pandas as pd
from faker import Faker

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
fake = Faker()
Faker.seed(SEED)

N_PROVIDERS = 400
N_PATIENTS = 6000
START_DATE = date(2024, 1, 1)
END_DATE = date(2025, 12, 31)
TOTAL_DAYS = (END_DATE - START_DATE).days

SPECIALTIES = [
    "Anxiety & Stress",
    "Depression",
    "Trauma & PTSD",
    "Couples Therapy",
    "Child & Adolescent",
    "Substance Use",
    "LGBTQ+ Affirming",
    "Grief & Loss",
]

STATES = ["NY", "CA", "TX", "FL", "IL", "PA", "NJ", "WA", "MA", "GA", "CO", "NC"]

# Specialties that are systematically under-supplied relative to demand.
# This creates the "story" the analysis is designed to surface.
HIGH_DEMAND_LOW_SUPPLY_SPECIALTIES = {"Child & Adolescent", "Substance Use"}

PAYERS = [
    ("Cigna/Evernorth", 0.94, 12),
    ("UnitedHealthcare", 0.90, 18),
    ("Aetna", 0.91, 16),
    ("BlueCross BlueShield", 0.88, 20),
    ("Optum", 0.93, 14),
    ("Self-Pay", 1.00, 0),
]


def random_date(start: date, end: date) -> date:
    delta_days = (end - start).days
    return start + timedelta(days=random.randint(0, delta_days))


# ---------------------------------------------------------------------------
# 1. Payers (small reference/dimension table)
# ---------------------------------------------------------------------------
def build_payers() -> pd.DataFrame:
    rows = []
    for payer_id, (name, approval_rate, avg_days_to_pay) in enumerate(PAYERS, start=1):
        rows.append(
            {
                "payer_id": payer_id,
                "payer_name": name,
                "base_approval_rate": approval_rate,
                "base_days_to_pay": avg_days_to_pay,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 2. Providers
# ---------------------------------------------------------------------------
def build_providers() -> pd.DataFrame:
    rows = []
    for i in range(1, N_PROVIDERS + 1):
        specialty = random.choice(SPECIALTIES)
        state = random.choices(
            STATES, weights=[18, 16, 12, 10, 8, 7, 6, 6, 5, 5, 4, 3]
        )[0]
        join_date = random_date(START_DATE, END_DATE - timedelta(days=30))

        # Providers in under-supplied specialties churn a bit more (burnout / overload)
        # to make the "supply gap" story realistic and visible in the data.
        is_scarce_specialty = specialty in HIGH_DEMAND_LOW_SUPPLY_SPECIALTIES
        churn_prob = 0.16 if is_scarce_specialty else 0.10

        is_active = random.random() > churn_prob
        churn_date = None
        if not is_active:
            min_churn = join_date + timedelta(days=60)
            if min_churn < END_DATE:
                churn_date = random_date(min_churn, END_DATE)
            else:
                is_active = True  # not enough runway to churn

        rows.append(
            {
                "provider_id": i,
                "provider_name": fake.name(),
                "specialty": specialty,
                "state": state,
                "join_date": join_date,
                "status": "active" if is_active else "churned",
                "churn_date": churn_date,
                "accepts_insurance": random.random() > 0.08,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 3. Patients
# ---------------------------------------------------------------------------
def build_patients(payers_df: pd.DataFrame) -> pd.DataFrame:
    payer_ids = payers_df["payer_id"].tolist()
    # Self-pay is rarer than insured
    payer_weights = [22, 20, 19, 18, 16, 5]

    rows = []
    for i in range(1, N_PATIENTS + 1):
        signup_date = random_date(START_DATE, END_DATE - timedelta(days=7))
        state = random.choices(
            STATES, weights=[18, 16, 12, 10, 8, 7, 6, 6, 5, 5, 4, 3]
        )[0]
        specialty_needed = random.choices(
            SPECIALTIES,
            # Demand skewed toward the scarce specialties -> creates real supply/demand gap
            weights=[14, 16, 12, 10, 16, 10, 8, 6],
        )[0]
        rows.append(
            {
                "patient_id": i,
                "signup_date": signup_date,
                "state": state,
                "specialty_needed": specialty_needed,
                "payer_id": random.choices(payer_ids, weights=payer_weights)[0],
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 4. Matches (patient matched to a provider; some matches fail/decline)
# ---------------------------------------------------------------------------
def build_matches(patients_df: pd.DataFrame, providers_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    match_id = 1

    providers_by_specialty = {
        spec: providers_df[providers_df["specialty"] == spec]
        for spec in SPECIALTIES
    }

    for _, patient in patients_df.iterrows():
        candidates = providers_by_specialty[patient["specialty_needed"]]
        is_scarce = patient["specialty_needed"] in HIGH_DEMAND_LOW_SUPPLY_SPECIALTIES

        if len(candidates) == 0:
            continue

        provider = candidates.sample(1).iloc[0]

        # Time-to-match is longer for scarce specialties -> the key insight
        if is_scarce:
            time_to_match_days = max(0, int(np.random.gamma(shape=4.0, scale=2.2)))
        else:
            time_to_match_days = max(0, int(np.random.gamma(shape=2.0, scale=1.3)))

        match_date = patient["signup_date"] + timedelta(days=time_to_match_days)
        if match_date > END_DATE:
            match_date = END_DATE

        # Outcome: accepted, declined_by_patient, declined_by_provider
        decline_prob = 0.18 if is_scarce else 0.10
        outcome_roll = random.random()
        if outcome_roll < decline_prob * 0.6:
            outcome = "declined_by_provider"
        elif outcome_roll < decline_prob:
            outcome = "declined_by_patient"
        else:
            outcome = "accepted"

        rows.append(
            {
                "match_id": match_id,
                "patient_id": patient["patient_id"],
                "provider_id": provider["provider_id"],
                "specialty": patient["specialty_needed"],
                "match_date": match_date,
                "time_to_match_days": time_to_match_days,
                "outcome": outcome,
            }
        )
        match_id += 1

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 5. Sessions (only for accepted matches; recurring weekly-ish sessions)
# ---------------------------------------------------------------------------
def build_sessions(
    matches_df: pd.DataFrame, payers_df: pd.DataFrame, patients_df: pd.DataFrame
) -> pd.DataFrame:
    payer_lookup = payers_df.set_index("payer_id").to_dict("index")
    patient_payer = patients_df.set_index("patient_id")["payer_id"].to_dict()

    rows = []
    session_id = 1
    accepted = matches_df[matches_df["outcome"] == "accepted"]

    for _, match in accepted.iterrows():
        payer_id = patient_payer[match["patient_id"]]
        payer_info = payer_lookup[payer_id]

        # Number of sessions this patient attends (retention proxy)
        n_sessions = max(1, int(np.random.gamma(shape=2.2, scale=3.0)))

        cursor = match["match_date"] + timedelta(days=random.randint(1, 5))
        for s in range(n_sessions):
            session_date = cursor + timedelta(days=7 * s + random.randint(-1, 2))
            if session_date > END_DATE:
                break

            billed_amount = round(random.uniform(120, 220), 2)

            approval_rate = payer_info["base_approval_rate"]
            is_approved = random.random() < approval_rate
            claim_status = "approved" if is_approved else "denied"

            denial_reason = None
            if claim_status == "denied":
                denial_reason = random.choice(
                    [
                        "missing_prior_auth",
                        "coding_error",
                        "out_of_network",
                        "session_limit_exceeded",
                        "eligibility_lapsed",
                    ]
                )

            days_to_pay = None
            reimbursed_amount = None
            if claim_status == "approved":
                days_to_pay = max(
                    1, int(np.random.normal(payer_info["base_days_to_pay"], 4))
                )
                reimbursed_amount = round(billed_amount * random.uniform(0.55, 0.85), 2)

            rows.append(
                {
                    "session_id": session_id,
                    "match_id": match["match_id"],
                    "patient_id": match["patient_id"],
                    "provider_id": match["provider_id"],
                    "payer_id": payer_id,
                    "session_date": session_date,
                    "billed_amount": billed_amount,
                    "claim_status": claim_status,
                    "denial_reason": denial_reason,
                    "days_to_pay": days_to_pay,
                    "reimbursed_amount": reimbursed_amount,
                }
            )
            session_id += 1

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    import os

    out_dir = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
    os.makedirs(out_dir, exist_ok=True)

    print("Generating payers...")
    payers_df = build_payers()

    print("Generating providers...")
    providers_df = build_providers()

    print("Generating patients...")
    patients_df = build_patients(payers_df)

    print("Generating matches...")
    matches_df = build_matches(patients_df, providers_df)

    print("Generating sessions...")
    sessions_df = build_sessions(matches_df, payers_df, patients_df)

    payers_df.to_csv(os.path.join(out_dir, "payers.csv"), index=False)
    providers_df.to_csv(os.path.join(out_dir, "providers.csv"), index=False)
    patients_df.to_csv(os.path.join(out_dir, "patients.csv"), index=False)
    matches_df.to_csv(os.path.join(out_dir, "matches.csv"), index=False)
    sessions_df.to_csv(os.path.join(out_dir, "sessions.csv"), index=False)

    print("\nDone. Row counts:")
    print(f"  payers:   {len(payers_df):,}")
    print(f"  providers:{len(providers_df):,}")
    print(f"  patients: {len(patients_df):,}")
    print(f"  matches:  {len(matches_df):,}")
    print(f"  sessions: {len(sessions_df):,}")


if __name__ == "__main__":
    main()
