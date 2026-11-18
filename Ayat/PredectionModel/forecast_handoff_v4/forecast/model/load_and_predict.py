"""Load the saved LightGBM weights and write a 15-day complaints forecast for one cutoff day.

Run from the forecast folder:
    .venv\\Scripts\\python.exe model\\load_and_predict.py                    # cutoff 2025-12-31 (default)
    .venv\\Scripts\\python.exe model\\load_and_predict.py 2025-12-31 out.csv

Needs only lightgbm, pandas, numpy, scipy, pyarrow. The feature code is copied from
04_Complaints_Forecast.ipynb (make_examples); keep the two in sync.
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
CARD = json.loads((HERE / "model_card.json").read_text(encoding="utf-8"))
FEATURES, CATS = CARD["features"], CARD["category_order"]
WINDOW, HORIZON = CARD["window_days"], CARD["horizon_days"]
HOLIDAYS = {pd.Timestamp(d) for d in CARD["holidays"]}
WEEKEND = set(CARD["weekend_dows"])

cutoff = pd.Timestamp(sys.argv[1] if len(sys.argv) > 1 else CARD["forecast_cutoff"])
out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "outputs" / f"forecast_from_{cutoff:%Y-%m-%d}.csv"

data = ROOT / "data"
if not (data / "req_prepared.parquet").exists():
    data = ROOT.parent / "oasis_mob_pss" / "data_clean"
req = pd.read_parquet(data / "req_prepared.parquet", columns=["date", "category_id"])
req["date"] = pd.to_datetime(req["date"])
days = pd.date_range(cutoff - pd.Timedelta(days=WINDOW + 7 * 6), cutoff, freq="D")
daily = req.groupby(["date", "category_id"]).size().unstack(fill_value=0).reindex(index=days, columns=CATS, fill_value=0)


def day_info(d):
    return {"dow": d.day_of_week, "is_weekend": int(d.day_of_week in WEEKEND), "is_holiday": int(d in HOLIDAYS)}


def make_examples(cutoff):
    window = daily.loc[cutoff - pd.Timedelta(days=WINDOW - 1): cutoff]
    weekend = window.index.day_of_week.isin(list(WEEKEND))
    rows = []
    for c in CATS:
        s = window[c]
        m7, m30 = s.iloc[-7:].mean(), s.mean()
        wk_ratio = (s[weekend].mean() + 0.5) / (s[~weekend].mean() + 0.5)
        for h in range(1, HORIZON + 1):
            target = cutoff + pd.Timedelta(days=h)
            same = [target - pd.Timedelta(days=7 * k) for k in range(1, 4 + 3)]
            same = [d for d in same if d <= cutoff][:4]
            rows.append({"date": target, "h": h, "category_id": c, **day_info(target),
                         "mean_7": m7, "mean_30": m30, "std_30": s.std(),
                         "same_dow_4w": s.loc[same].mean(), "trend": (m7 + 0.5) / (m30 + 0.5),
                         "weekend_ratio": wk_ratio})
    df = pd.DataFrame(rows)
    df["category_id"] = pd.Categorical(df["category_id"], categories=CATS)
    return df


model = lgb.Booster(model_file=str(HERE / CARD["model_file"]))
ex = make_examples(cutoff)
mu = model.predict(ex[FEATURES])
forecast = ex[["date", "category_id"]].assign(
    category_id=lambda d: d["category_id"].astype(str),
    pillar=lambda d: d["category_id"].map(CARD["pillar"]),
    forecast=np.round(mu, 1), low_80=poisson.ppf(0.1, mu).astype(int), high_80=poisson.ppf(0.9, mu).astype(int),
    model="LightGBM (poisson), trained on Jul–Dec 2025, synthetic data")
forecast.to_csv(out_path, index=False)
print(f"Wrote {len(forecast)} rows to {out_path}")
