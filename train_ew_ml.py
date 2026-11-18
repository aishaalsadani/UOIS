"""train_ew_ml.py: Standalone training pipeline for Early Warning ML Verifier.

Trains a lightweight RandomForestClassifier to predict True Anomaly vs False Alarm
for incoming Early Warning signals based on telemetry and incident features.
Outputs: ml_ew_model.pkl
"""

from __future__ import annotations

import os
import pickle
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import train_test_split

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_OUT = os.path.join(MODULE_DIR, "ml_ew_model.pkl")

def generate_ew_synthetic_data(n_samples: int = 5000, random_seed: int = 42) -> pd.DataFrame:
    """Generate realistic physical telemetry and Early Warning incident profiles."""
    np.random.seed(random_seed)

    zones = ["Z01", "Z02", "Z03", "Z04", "Z05", "Z06"]
    priorities = ["Low", "Medium", "High", "Critical"]
    sla_statuses = ["Within_SLA", "At_Risk", "Breached"]

    zone_choices = np.random.choice(zones, size=n_samples, p=[0.22, 0.18, 0.20, 0.15, 0.13, 0.12])
    priority_choices = np.random.choice(priorities, size=n_samples, p=[0.25, 0.40, 0.25, 0.10])
    sla_choices = np.random.choice(sla_statuses, size=n_samples, p=[0.60, 0.28, 0.12])
    hours = np.random.randint(0, 24, size=n_samples)

    # Physical inlet pressure (bar): Normal ~ 3.5 - 4.5. Faults: < 2.2 or > 5.3
    pressures = np.random.normal(loc=3.85, scale=0.95, size=n_samples)
    pressures = np.clip(pressures, 0.6, 7.2)

    # Deterministic ground truth weighting with stochastic noise
    labels = []
    for p, prio, sla, h in zip(pressures, priority_choices, sla_choices, hours):
        is_pressure_anomaly = (p < 2.3) or (p > 5.2)

        score = 0.05
        if is_pressure_anomaly:
            score += 0.60
        if prio in ["High", "Critical"]:
            score += 0.22
        if sla == "Breached":
            score += 0.10
        if 8 <= h <= 18:
            score += 0.05

        prob_true = np.clip(score + np.random.normal(0, 0.07), 0.02, 0.98)
        labels.append(1 if prob_true >= 0.50 else 0)

    return pd.DataFrame({
        "sensor_pressure_bar": pressures.round(2),
        "priority": priority_choices,
        "zone_id": zone_choices,
        "hour": hours,
        "SLA_status": sla_choices,
        "is_genuine_alarm": labels
    })

def train_and_export():
    print("[*] Generating synthetic Early Warning telemetry dataset...")
    df = generate_ew_synthetic_data()
    print(f"    Total records: {len(df)} | Genuine alarms: {df['is_genuine_alarm'].sum()} | False alarms: {(df['is_genuine_alarm'] == 0).sum()}")

    priority_map = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
    sla_map = {"Within_SLA": 0, "At_Risk": 1, "Breached": 2}
    zone_map = {f"Z0{i}": i for i in range(1, 7)}

    X = pd.DataFrame({
        "sensor_pressure_bar": df["sensor_pressure_bar"],
        "priority": df["priority"].map(priority_map),
        "zone_id": df["zone_id"].map(zone_map),
        "hour": df["hour"],
        "SLA_status": df["SLA_status"].map(sla_map)
    })
    y = df["is_genuine_alarm"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.20, random_state=42, stratify=y)

    print("[*] Training Early Warning RandomForestClassifier...")
    clf = RandomForestClassifier(
        n_estimators=50,
        max_depth=6,
        min_samples_split=4,
        random_state=42,
        n_jobs=-1
    )
    clf.fit(X_train, y_train)

    preds = clf.predict(X_test)
    probs = clf.predict_proba(X_test)[:, 1]

    print("\n" + "=" * 65)
    print("EARLY WARNING ML VERIFIER - EVALUATION REPORT")
    print("=" * 65)
    print(classification_report(y_test, preds, target_names=["False Alarm (Debunked)", "True Anomaly (Confirmed)"]))
    print(f"ROC-AUC Score: {roc_auc_score(y_test, probs):.4f}")
    print("=" * 65)

    bundle = {
        "model": clf,
        "features": list(X.columns),
        "priority_map": priority_map,
        "sla_map": sla_map,
        "zone_map": zone_map,
        "trained_at": pd.Timestamp.now().isoformat(),
        "n_samples": len(df)
    }

    with open(MODEL_OUT, "wb") as f:
        pickle.dump(bundle, f, protocol=pickle.HIGHEST_PROTOCOL)

    print(f"\n[+] Trained ML model successfully saved to:\n    {MODEL_OUT}\n")

if __name__ == "__main__":
    train_and_export()