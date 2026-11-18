# Complaints Simulator (60 days) — handoff

<div dir="rtl">

**ملخص:** النظام ده بيتوقع لكل منطقة (Z01–Z06) × نوع شكوى (15) × يوم (1 يناير → 1 مارس 2026) عدد الشكاوى، ومعاه أحسن حالة (P10) وأسوأ حالة (P90). وفيه 4 سيناريوهات: الطبيعي، ورمضان، وحل مشكلة، وزيادة سكان.

**لأي موقع:** اقرا ملفات `outputs/*.csv` / `.json`، أو استدعي `simulate(...)` من `simulator_api.py`. ومتشغّلش الموديل جوه الموقع.

</div>

## 1. Folder contents

| Path | What it is |
|---|---|
| `05_Complaints_Simulator_60d.ipynb` / `.html` | The notebook (Arabic explanations, English code), executed. The HTML opens in any browser. |
| `MODEL_REPORT_60d.md` | Everything: data, assumptions, models, tests, results, simulator, scenarios, limitations, changelog |
| `simulator_api.py` | `simulate(zone, days, view, scenario, **params)`; reads the CSVs and the model card only |
| `data/` | `req_prepared.parquet`, `calendar.parquet`, `dim_zones.parquet` (copies from `oasis_mob_pss/data_clean`) |
| `outputs/zone_forecast_60d.csv` / `.json` | **Daily forecast:** 5,400 rows (6 zones × 15 types × 60 days) |
| `outputs/zone_forecast_60d_weekly.csv` | Weekly sums with P10/P50/P90 (week 9 = days 57–60) |
| `outputs/zone_forecast_60d_monthly.csv` | Calendar-month sums with P10/P50/P90 (March = 1 day) |
| `outputs/zone_forecast_60d_ramadan_off.csv` | Means with Ramadan off (used by `simulate`) |
| `outputs/accuracy_60d.csv` | Test accuracy by model, view, level, zone and N |
| `outputs/backtest_60d.csv` | Test predictions vs actuals |
| `outputs/simulator_coverage_60d.csv` | P10–P90 coverage of the simulator in the tests |
| `outputs/scenario_examples_60d.csv` | The three worked scenario examples |
| `model/lightgbm_60d.txt` | **Model weights** (LightGBM, 400 trees) |
| `model/model_card_60d.json` | Feature order, zone and type order, parameters, assumptions, simulator settings, population |
| `model/load_and_predict_60d.py` | Rebuilds the daily `mean` column from the weights (verified identical) |

## 2. How to run

The notebook needs pandas, pyarrow, numpy, scipy, matplotlib, lightgbm, jupyter, nbconvert and ipykernel. These are the same pinned versions as `forecast/requirements.txt`:
- pandas 3.1.0, pyarrow 26.0.0, numpy 2.5.4, scipy 1.18.1, matplotlib 3.11.2;
- lightgbm 4.7.0;
- jupyter 1.1.1, nbconvert 7.17.2, ipykernel 7.4.0.

Run from inside the `forecast_60d` folder:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install pandas==3.1.0 pyarrow==26.0.0 numpy==2.5.4 scipy==1.18.1 matplotlib==3.11.2 lightgbm==4.7.0 jupyter==1.1.1 nbconvert==7.17.2 ipykernel==7.4.0
.venv\Scripts\jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=5400 05_Complaints_Simulator_60d.ipynb
.venv\Scripts\jupyter nbconvert --to html 05_Complaints_Simulator_60d.ipynb
```

A full run takes several minutes. `simulator_api.py` itself needs only pandas, numpy and scipy.

## 3. `simulate(...)`

```python
from simulator_api import simulate      # run from the forecast_60d folder

r = simulate("Z01", days=30, view="weekly")                                   # normal
r = simulate("ALL", days=60, view="monthly", scenario="ramadan_off")          # Ramadan effect
r = simulate("Z01", days=60, scenario="fix", category="streetlights", start_date="2026-01-15", reduce_pct=30)
r = simulate("Z04", days=60, scenario="population", new_population=9000)
```

| Argument | Values |
|---|---|
| `zone` | `"ALL"`, or `"Z01"` … `"Z06"` |
| `days` | Whole number from 1 to 60 (counted from 2026-01-01) |
| `view` | `"daily"`, `"weekly"` (7-day blocks) or `"monthly"` (calendar months) |
| `scenario` | `"normal"`, `"ramadan_off"`, `"fix"`, `"population"` |
| `fix` params | `category` (one of the 15 ids), `start_date` (`"YYYY-MM-DD"`), `reduce_pct` (0–100). The fix zone is `zone`, or `fix_zone` if `zone="ALL"`. |
| `population` params | `new_population` (> 0). The zone is `zone`, or `pop_zone` if `zone="ALL"`. |
| Optional | `n_sims` (default 1000), `seed` (default 42) |

**It returns a dict:**

| Key | Content |
|---|---|
| `by_type` | Each type over all selected days, most complaints first |
| `by_period` | Totals per day, week or month |
| `detail` | Period × zone × type |
| `total` | The overall total |
| `by_zone` | Only for `"ALL"`: totals per zone |
| `assumptions` | Text of the assumptions used |
| `scenario`, `zone`, `days`, `view`, `dates` | Echo of the request |

**Columns** in every table:
- `normal_mean`, `normal_p10`, `normal_p90`;
- `mean`, `p10`, `p90` (the scenario);
- `change`, `change_pct`.

For `"normal"` the scenario columns equal the normal ones.

Invalid input raises `ValueError` with a clear message.

## 4. Data contract: `outputs/zone_forecast_60d.csv` (and `.json`, the same records)

| Column | Type | Meaning |
|---|---|---|
| `zone` | string | `Z01` … `Z06` |
| `date` | `YYYY-MM-DD` | 2026-01-01 … 2026-03-01 |
| `day_number` | int 1–60 | Days after the cutoff (2025-12-31). Filter `day_number <= N` for the next N days. |
| `category_id` | string | One of the 15 types (below) |
| `pillar` | string | Sector of the type |
| `mean` | float | Expected complaints that day (model output) |
| `p10`, `p50`, `p90` | number | Best case, median and worst case for that day, from 1,000 simulator draws |

**Multi-day totals:** sum `mean`, but do **not** sum `p10` or `p90`. Use the weekly and monthly files or `simulate(...)`, which add up the draws correctly.

**Types and pillars:**

| category_id | pillar |
|---|---|
| app | citizen_services |
| hvac | buildings |
| power_outage | energy |
| noise | environment |
| parks | environment |
| parking | mobility |
| roads | mobility |
| traffic_signals | mobility |
| safety | public_safety |
| streetlights | public_safety |
| cleanliness | waste |
| waste_overflow | waste |
| sewer | water |
| water_leak | water |
| water_outage | water |

The BERT classifier (if used upstream) must output exactly these `category_id` strings.

## 5. Accuracy to quote

This is LGB-all-year in Exam B (1 Nov–30 Dec 2025), the test comparable to the final model:

| View | Each type in each zone | Zone total | Each type, whole city |
|---|---|---|---|
| Daily | 47.2% | 85.6% | 76.3% |
| Weekly | 79.1% | 93.5% | 89.3% |
| Monthly (30 days) | 87.0% | 95.6% | 92.6% |

**Caveat:** in Exam A (Sep–Oct) the simple Baseline did better, because the model had not yet seen a full month after the app launch. See `MODEL_REPORT_60d.md` §6.

## 6. Refreshing

1. Replace `data/req_prepared.parquet` with newer data, and extend `calendar.parquet` for new holidays and Ramadan.
2. In the notebook, move `LAST_DAY` and the assumptions in section 1, and the test cutoffs in section 5.
3. Re-run the notebook. The output file names stay the same, so `simulator_api.py` picks up the new forecast automatically.
