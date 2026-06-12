import logging
import os

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

logger = logging.getLogger(__name__)

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")


def _ensure_models_dir():
    os.makedirs(MODELS_DIR, exist_ok=True)


def train_budget_overrun(records: list[dict]) -> None:
    df = pd.DataFrame(records)
    if len(df) < 2:
        logger.warning("ML_TRAIN | budget_overrun | skipped — not enough data")
        return

    features = ["spend_rate", "incident_count", "log_count", "days_elapsed", "typhoon_log_ratio"]
    X = df[features].fillna(0).astype(float)
    y = df["is_over_budget"].astype(int)

    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X, y)

    _ensure_models_dir()
    joblib.dump(model, os.path.join(MODELS_DIR, "budget_overrun.joblib"))
    logger.info(f"ML_TRAIN | budget_overrun | trained | samples={len(df)}")


def train_delay_risk(records: list[dict]) -> None:
    df = pd.DataFrame(records)
    if len(df) < 2:
        logger.warning("ML_TRAIN | delay_risk | skipped — not enough data")
        return

    features = ["log_count", "avg_hours", "incident_rate", "typhoon_log_ratio", "days_elapsed", "days_remaining", "is_active", "structure_slipping"]
    X = df[features].fillna(0).astype(float)
    # Delay risk score: weighted combination of signals
    df = df.astype({col: float for col in features + ["structure_slipping", "incident_rate", "typhoon_log_ratio", "avg_hours"]})
    y = (
        df["structure_slipping"] * 0.4
        + df["incident_rate"].clip(0, 1) * 0.3
        + df["typhoon_log_ratio"].clip(0, 1) * 0.2
        + (1 - (df["avg_hours"] / 10).clip(0, 1)) * 0.1
    ).clip(0, 1)

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)

    _ensure_models_dir()
    joblib.dump(model, os.path.join(MODELS_DIR, "delay_risk.joblib"))
    logger.info(f"ML_TRAIN | delay_risk | trained | samples={len(df)}")


def train_material_forecast(records: list[dict]) -> None:
    df = pd.DataFrame(records).dropna(subset=["monthly_cost"])
    if len(df) < 6:
        logger.warning("ML_TRAIN | material_forecast | skipped — not enough data")
        return

    # Add rolling average feature per project
    df = df.sort_values(["project_id", "year", "month"])
    df["rolling_avg_3m"] = df.groupby("project_id")["monthly_cost"].transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean()).fillna(0)

    features = ["month", "quarter", "rolling_avg_3m", "q3_2024_spike", "q2_2025_spike", "is_typhoon_month"]
    X = df[features].fillna(0).astype(float)
    y = df["monthly_cost"].astype(float)

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)

    _ensure_models_dir()
    joblib.dump(model, os.path.join(MODELS_DIR, "material_forecast.joblib"))
    logger.info(f"ML_TRAIN | material_forecast | trained | samples={len(df)}")
