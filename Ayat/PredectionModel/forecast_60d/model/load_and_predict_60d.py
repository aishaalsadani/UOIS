"""Rebuild the 60-day mean forecast (zone × type × day) from the saved LightGBM weights, without retraining.

Run from the forecast_60d folder:
    ..\\forecast\\.venv\\Scripts\\python.exe model\\load_and_predict_60d.py                 # cutoff 2025-12-31
    ..\\forecast\\.venv\\Scripts\\python.exe model\\load_and_predict_60d.py 2025-12-31 out.csv

Writes zone, date, day_number, category_id, pillar, mean (same rounding as outputs/zone_forecast_60d.csv).
Needs only lightgbm, pandas, numpy, pyarrow. The feature code is copied from 05_Complaints_Simulator_60d.ipynb
(make_examples); keep the two in sync.
"""
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CARD = json.loads((HERE / "model_card_60d.json").read_text(encoding="utf-8"))
FEATURES, ZONES, CATS = CARD["features"], CARD["zone_order"], CARD["category_order"]
WINDOW, HORIZON, SMOOTH = CARD["window_days"], CARD["horizon_days"], CARD["share_smoothing"]
HOLIDAYS = {pd.Timestamp(d) for d in CARD["holidays"]}
RAMADAN = {pd.Timestamp(d) for d in CARD["ramadan_days"]}
WEEKEND = list(CARD["weekend_dows"])
APP_LAUNCH = pd.Timestamp(CARD["app_launch"])
NZ, NT = len(ZONES), len(CATS)

cutoff = pd.Timestamp(sys.argv[1] if len(sys.argv) > 1 else CARD["forecast_cutoff"])
out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "outputs" / f"forecast_60d_from_{cutoff:%Y-%m-%d}.csv"

data = ROOT / "data"
if not (data / "req_prepared.parquet").exists():
    data = ROOT.parent / "oasis_mob_pss" / "data_clean"
req = pd.read_parquet(data / "req_prepared.parquet", columns=["date", "zone_id", "category_id"]).dropna(subset=["zone_id"])
req["date"] = pd.to_datetime(req["date"])
DAYS = pd.date_range(cutoff - pd.Timedelta(days=WINDOW + 7 * 13), cutoff, freq="D")
POS = {d: i for i, d in enumerate(DAYS)}
Z = (req.groupby(["date", "zone_id", "category_id"]).size()
     .reindex(pd.MultiIndex.from_product([DAYS, ZONES, CATS]), fill_value=0).to_numpy().reshape(len(DAYS), NZ, NT))

H_ = np.arange(1, HORIZON + 1)
SAME_K = np.array([[-(-h // 7) + j for j in range(4)] for h in H_])

i = POS[cutoff]
W = Z[i - WINDOW + 1: i + 1].astype(float)
wdays = DAYS[i - WINDOW + 1: i + 1]
wk = wdays.day_of_week.isin(WEEKEND)
m7, m30, sd = W[-7:].mean(0), W.mean(0), W.std(0, ddof=1)
wr = (W[wk].mean(0) + 0.5) / (W[~wk].mean(0) + 0.5)
city = W.sum(1)
share = (W.sum(0) + SMOOTH) / (city.sum(0) + SMOOTH * NZ)
ztot = np.repeat(W.sum(2).mean(0), NT).reshape(NZ, NT)
same = Z[i + H_[:, None] - 7 * SAME_K].mean(1)
targets = cutoff + pd.to_timedelta(H_, unit="D")
b = lambda a: np.broadcast_to(np.asarray(a, dtype=float), (HORIZON, NZ, NT)).ravel()
rep = lambda a: np.repeat(np.asarray(a), NZ * NT)
X = pd.DataFrame({
    "h": rep(H_), "zone_id": np.tile(np.repeat(ZONES, NT), HORIZON), "category_id": np.tile(CATS, NZ * HORIZON),
    "dow": rep(targets.day_of_week), "is_weekend": rep(targets.day_of_week.isin(WEEKEND).astype(int)),
    "is_holiday": rep([int(d in HOLIDAYS) for d in targets]), "is_ramadan": rep([int(d in RAMADAN) for d in targets]),
    "post_app": rep((targets >= APP_LAUNCH).astype(int)),
    "window_post_app_share": float((wdays >= APP_LAUNCH).mean()),
    "mean_7": b(m7), "mean_30": b(m30), "std_30": b(sd), "same_dow_4w": same.ravel(),
    "trend": b((m7 + 0.5) / (m30 + 0.5)), "weekend_ratio": b(wr),
    "city_mean_30": b(np.broadcast_to(city.mean(0), (NZ, NT))), "zone_share_30": b(share), "zone_total_mean_30": b(ztot)})
X["zone_id"] = pd.Categorical(X["zone_id"], categories=ZONES)
X["category_id"] = pd.Categorical(X["category_id"], categories=CATS)
mu = lgb.Booster(model_file=str(HERE / CARD["model_file"])).predict(X[FEATURES])
out = pd.DataFrame({"zone": X["zone_id"].astype(str), "date": np.repeat(targets.strftime("%Y-%m-%d"), NZ * NT),
                    "day_number": X["h"], "category_id": X["category_id"].astype(str),
                    "pillar": X["category_id"].astype(str).map(CARD["pillar"]), "mean": np.round(mu, 4)})
out = out.sort_values(["zone", "day_number", "category_id"], ignore_index=True)
out.to_csv(out_path, index=False)
print(f"Wrote {len(out)} rows to {out_path}")
