import logging
import os

import joblib
import pandas as pd

logger = logging.getLogger(__name__)

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")


def _load(filename: str):
    path = os.path.join(MODELS_DIR, filename)
    if not os.path.exists(path):
        logger.warning(f"ML_PREDICT | model not found | file={filename}")
        return None
    return joblib.load(path)


def predict_budget_overrun(records: list[dict]) -> list[dict]:
    model = _load("budget_overrun.joblib")
    if not model or not records:
        return []

    df = pd.DataFrame(records)
    features = ["spend_rate", "incident_count", "log_count", "days_elapsed", "typhoon_log_ratio"]
    X = df[features].fillna(0).astype(float)

    proba = model.predict_proba(X)[:, 1]  # probability of overrun
    results = []
    for i, row in df.iterrows():
        results.append(
            {
                "project_id": int(row["project_id"]),
                "project_name": row["project_name"],
                "overrun_probability": round(float(proba[i]), 3),
                "is_over_budget": bool(row["is_over_budget"]),
                "total_budget": float(row["total_budget"]),
                "total_spent": float(row["total_spent"]),
            }
        )
    return results


def predict_delay_risk(records: list[dict]) -> list[dict]:
    model = _load("delay_risk.joblib")
    if not model or not records:
        return []

    df = pd.DataFrame(records)
    features = ["log_count", "avg_hours", "incident_rate", "typhoon_log_ratio", "days_elapsed", "days_remaining", "is_active", "structure_slipping"]
    X = df[features].fillna(0).astype(float)

    scores = model.predict(X).clip(0, 1)
    results = []
    for i, row in df.iterrows():
        score = float(scores[i])
        results.append(
            {
                "project_id": int(row["project_id"]),
                "project_name": row["project_name"],
                "delay_risk_score": round(score, 3),
                "risk_level": "High" if score >= 0.6 else "Medium" if score >= 0.3 else "Low",
            }
        )
    return results


def predict_material_forecast(records: list[dict]) -> list[dict]:
    model = _load("material_forecast.joblib")
    if not model or not records:
        return []

    df = pd.DataFrame(records).sort_values(["project_id", "year", "month"])
    df["rolling_avg_3m"] = df.groupby("project_id")["monthly_cost"].transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean()).fillna(0)

    # Predict next month for each project using last known row
    last_rows = df.groupby("project_id").last().reset_index()

    # Shift month forward by 1
    last_rows["month"] = (last_rows["month"] % 12) + 1
    last_rows["quarter"] = ((last_rows["month"] - 1) // 3) + 1
    last_rows["is_typhoon_month"] = last_rows["month"].isin([7, 8, 9, 10]).astype(int)
    last_rows["q3_2024_spike"] = 0
    last_rows["q2_2025_spike"] = 0

    features = ["month", "quarter", "rolling_avg_3m", "q3_2024_spike", "q2_2025_spike", "is_typhoon_month"]
    X = last_rows[features].fillna(0).astype(float)
    forecasts = model.predict(X)

    results = []
    for i, row in last_rows.iterrows():
        results.append(
            {
                "project_id": int(row["project_id"]),
                "project_name": row["project_name"],
                "forecast_month": int(row["month"]),
                "predicted_cost": round(float(forecasts[i]), 2),
            }
        )
    return results
