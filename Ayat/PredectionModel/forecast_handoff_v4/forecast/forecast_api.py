"""get_forecast(zone, days): read the ready zone forecast and answer "how many complaints of which type, where".

Usage (from the forecast folder):
    from forecast_api import get_forecast
    r = get_forecast("Z01", days=5)
    r["by_type"], r["daily"], r["total"], r["accuracy"]          # one zone
    r = get_forecast("ALL", days=7)
    r["by_zone"], r["zone_type"]                                  # extra tables for all zones

Only reads two CSV files from outputs/ (no model, no LightGBM needed).
"""
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import poisson

OUT = Path(__file__).resolve().parent / "outputs"
FORECAST_FILE = OUT / "zone_forecast_2026-01-01_to_15.csv"
ACCURACY_FILE = OUT / "zone_accuracy_by_days.csv"


@lru_cache(maxsize=1)
def _load():
    return pd.read_csv(FORECAST_FILE), pd.read_csv(ACCURACY_FILE)


def _range(mu):
    mu = np.maximum(np.asarray(mu, dtype=float), 1e-9)
    return poisson.ppf(0.1, mu).astype(int), poisson.ppf(0.9, mu).astype(int)


def get_forecast(zone="ALL", days=15):
    fc, acc = _load()
    zones = sorted(fc["zone"].unique())
    max_days = int(fc["day_number"].max())
    if zone != "ALL" and zone not in zones:
        raise ValueError(f"zone must be 'ALL' or one of {zones}, got {zone!r}")
    if isinstance(days, bool) or not isinstance(days, (int, np.integer)) or not 1 <= days <= max_days:
        raise ValueError(f"days must be a whole number from 1 to {max_days}, got {days!r}")

    sel = fc[fc["day_number"] <= days]
    if zone != "ALL":
        sel = sel[sel["zone"] == zone]
    method = fc["model"].iloc[0]

    by_type = sel.groupby(["category_id", "pillar"], as_index=False)["forecast"].sum()
    by_type["low_80"], by_type["high_80"] = _range(by_type["forecast"])
    by_type = by_type.sort_values("forecast", ascending=False, ignore_index=True)
    by_type["forecast"] = by_type["forecast"].round(1)

    daily = sel.pivot_table(index="category_id", columns="date", values="forecast", aggfunc="sum").round(1)
    daily = daily.loc[by_type["category_id"]]

    total = float(sel["forecast"].sum())
    lo, hi = _range([total])
    a = acc[(acc["method"] == method) & (acc["level"] == "zone x type") & (acc["zone"] == zone) & (acc["days"] == days)]
    out = {
        "zone": zone, "days": days, "dates": [sel["date"].min(), sel["date"].max()], "method": method,
        "by_type": by_type, "daily": daily,
        "total": {"forecast": round(total, 1), "low_80": int(lo[0]), "high_80": int(hi[0])},
        "accuracy": {"accuracy_%": float(a["accuracy"].iloc[0]), "mae": float(a["mae"].iloc[0]),
                     "coverage_%": float(a["coverage"].iloc[0]),
                     "measured_on": "Nov–Dec 2025 tests, each type in the zone summed over the chosen days"},
    }
    if zone == "ALL":
        by_zone = sel.groupby("zone", as_index=False)["forecast"].sum()
        by_zone["low_80"], by_zone["high_80"] = _range(by_zone["forecast"])
        out["by_zone"] = by_zone.sort_values("forecast", ascending=False, ignore_index=True).round({"forecast": 1})
        zt = sel.pivot_table(index="zone", columns="category_id", values="forecast", aggfunc="sum")
        out["zone_type"] = zt.loc[out["by_zone"]["zone"], by_type["category_id"]].round(1)
        zt_acc = acc[(acc["method"] == method) & (acc["level"] == "zone total") & (acc["zone"] == "ALL") & (acc["days"] == days)]
        out["accuracy"]["zone_total_accuracy_%"] = float(zt_acc["accuracy"].iloc[0])
    return out


if __name__ == "__main__":
    r = get_forecast("ALL", days=7)
    print(r["dates"], r["total"], r["accuracy"])
    print(r["by_zone"])
