"""Rebuild the 15-day forecast per zone × complaint type from the saved weights (no retraining).

Run from the forecast folder:
    .venv\\Scripts\\python.exe model\\load_and_predict_zone.py                    # cutoff 2025-12-31, method from the card
    .venv\\Scripts\\python.exe model\\load_and_predict_zone.py 2025-12-31 out.csv
    .venv\\Scripts\\python.exe model\\load_and_predict_zone.py 2025-12-31 out.csv LightGBM-zone

Methods (model_card_zone.json -> "forecast_method" is the one used for outputs/zone_forecast_*.csv):
- Top-down:      city LightGBM (lightgbm_complaints_forecast.txt) per type × each zone's share of that type
                 over the last 60 days <= cutoff.
- LightGBM-zone: the zone LightGBM (lightgbm_zone_forecast.txt) on zone × type features.
Needs only lightgbm, pandas, numpy, scipy, pyarrow. The feature code is copied from 04_Complaints_Forecast.ipynb
(make_examples, zone_examples); keep them in sync.
"""
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import poisson

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CARD = json.loads((HERE / "model_card_zone.json").read_text(encoding="utf-8"))
CITY_CARD = json.loads((HERE / CARD["top_down"]["city_model_card"]).read_text(encoding="utf-8"))
ZONES, CATS = CARD["zone_order"], CARD["category_order"]
WINDOW, HORIZON, SMOOTH = CARD["window_days"], CARD["horizon_days"], CARD["share_smoothing"]
HOLIDAYS = {pd.Timestamp(d) for d in CARD["holidays"]}
WEEKEND = set(CARD["weekend_dows"])
NZ, NT = len(ZONES), len(CATS)

cutoff = pd.Timestamp(sys.argv[1] if len(sys.argv) > 1 else CARD["forecast_cutoff"])
out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "outputs" / f"zone_forecast_from_{cutoff:%Y-%m-%d}.csv"
method = sys.argv[3] if len(sys.argv) > 3 else CARD["forecast_method"]

data = ROOT / "data"
if not (data / "req_prepared.parquet").exists():
    data = ROOT.parent / "oasis_mob_pss" / "data_clean"
req = pd.read_parquet(data / "req_prepared.parquet", columns=["date", "category_id", "zone_id"]).dropna(subset=["zone_id"])
req["date"] = pd.to_datetime(req["date"])
days = pd.date_range(cutoff - pd.Timedelta(days=90), cutoff, freq="D")
idx = pd.MultiIndex.from_product([days, ZONES, CATS])
Z = req.groupby(["date", "zone_id", "category_id"]).size().reindex(idx, fill_value=0).to_numpy().reshape(len(days), NZ, NT)
POS = {d: i for i, d in enumerate(days)}


def day_info(d):
    return {"dow": d.day_of_week, "is_weekend": int(d.day_of_week in WEEKEND), "is_holiday": int(d in HOLIDAYS)}


def same_weekday(target):
    same = [target - pd.Timedelta(days=7 * k) for k in range(1, 7)]
    return [POS[d] for d in same if d <= cutoff][:4]


def city_examples():
    # City-level features (copy of make_examples in the notebook), row order: type, then h.
    city = Z.sum(1)                                              # day × type
    i = POS[cutoff]
    W = city[i - WINDOW + 1: i + 1].astype(float)
    wk = days[i - WINDOW + 1: i + 1].day_of_week.isin(list(WEEKEND))
    rows = []
    for t, c in enumerate(CATS):
        s = W[:, t]
        m7, m30 = s[-7:].mean(), s.mean()
        wk_ratio = (s[wk].mean() + 0.5) / (s[~wk].mean() + 0.5)
        for h in range(1, HORIZON + 1):
            target = cutoff + pd.Timedelta(days=h)
            rows.append({"category_id": c, "h": h, **day_info(target), "mean_7": m7, "mean_30": m30,
                         "std_30": s.std(ddof=1), "same_dow_4w": city[same_weekday(target), t].mean(),
                         "trend": (m7 + 0.5) / (m30 + 0.5), "weekend_ratio": wk_ratio})
    df = pd.DataFrame(rows)
    df["category_id"] = pd.Categorical(df["category_id"], categories=CITY_CARD["category_order"])
    return df


def zone_examples():
    i = POS[cutoff]
    W = Z[i - WINDOW + 1: i + 1].astype(float)
    wk = days[i - WINDOW + 1: i + 1].day_of_week.isin(list(WEEKEND))
    m7, m30, sd = W[-7:].mean(0), W.mean(0), W.std(0, ddof=1)
    wr = (W[wk].mean(0) + 0.5) / (W[~wk].mean(0) + 0.5)
    city = W.sum(1)
    share = (W.sum(0) + SMOOTH) / (city.sum(0) + SMOOTH * NZ)
    ztot = np.repeat(W.sum(2).mean(0), NT)
    parts = []
    for h in range(1, HORIZON + 1):
        target = cutoff + pd.Timedelta(days=h)
        parts.append(pd.DataFrame({
            "h": h, "zone_id": np.repeat(ZONES, NT), "category_id": np.tile(CATS, NZ), **day_info(target),
            "mean_7": m7.ravel(), "mean_30": m30.ravel(), "std_30": sd.ravel(),
            "same_dow_4w": Z[same_weekday(target)].mean(0).ravel(), "trend": ((m7 + 0.5) / (m30 + 0.5)).ravel(),
            "weekend_ratio": wr.ravel(),
            "city_mean_7": np.tile(city[-7:].mean(0), NZ), "city_mean_30": np.tile(city.mean(0), NZ),
            "zone_share_30": share.ravel(), "zone_total_mean_30": ztot}))
    df = pd.concat(parts, ignore_index=True)
    df["zone_id"] = pd.Categorical(df["zone_id"], categories=ZONES)
    df["category_id"] = pd.Categorical(df["category_id"], categories=CATS)
    return df


if method == "Top-down":
    city_model = lgb.Booster(model_file=str(HERE / CARD["top_down"]["city_model_file"]))
    ce = city_examples()
    mu_city = city_model.predict(ce[CITY_CARD["features"]]).reshape(NT, HORIZON)        # type × h
    i, n = POS[cutoff], CARD["top_down"]["share_window_days"]
    W = Z[i - n + 1: i + 1].sum(0).astype(float)                                       # zone × type
    tot = W.sum(0)
    share = np.where(tot > 0, W / np.where(tot > 0, tot, 1), 1 / NZ)
    mu = (share[:, :, None] * mu_city[None, :, :]).transpose(2, 0, 1).ravel()           # h, zone, type
elif method == "LightGBM-zone":
    mu = lgb.Booster(model_file=str(HERE / CARD["model_file"])).predict(zone_examples()[CARD["features"]])
else:
    raise ValueError(f"unknown method {method!r}")

h, z, t = np.meshgrid(np.arange(1, HORIZON + 1), ZONES, CATS, indexing="ij")
forecast = pd.DataFrame({
    "zone": z.ravel(), "date": (cutoff + pd.to_timedelta(h.ravel(), unit="D")).strftime("%Y-%m-%d"),
    "day_number": h.ravel(), "category_id": t.ravel(), "pillar": pd.Series(t.ravel()).map(CARD["pillar"]),
    "forecast": np.round(mu, 2),
    "low_80": poisson.ppf(0.1, np.maximum(mu, 1e-9)).astype(int),
    "high_80": poisson.ppf(0.9, np.maximum(mu, 1e-9)).astype(int),
    "model": method}).sort_values(["zone", "day_number", "category_id"], ignore_index=True)
forecast.to_csv(out_path, index=False)
print(f"Wrote {len(forecast)} rows to {out_path} (method {method})")
