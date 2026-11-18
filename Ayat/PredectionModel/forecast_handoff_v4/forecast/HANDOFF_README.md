# Complaints Forecast — handoff package

<div dir="rtl">

**ملخص سريع:** الموديل ده بيتوقع عدد الشكاوى لكل نوع من الـ 15 نوع، لكل يوم من الـ 15 يوم الجايين، بناءً على آخر 30 يوم. الموديل المختار **LightGBM (poisson)**، ودقته 76.7% لكل نوع في كل يوم، وده قريب من أقصى دقة ممكنة (~77%) بسبب العشوائية الطبيعية في الأرقام. على مستوى إجمالي المدينة في اليوم الدقة ~94%، وعلى إجمالي كل نوع في الـ 15 يوم ~93%.
**جديد، توقع المناطق:** تختار منطقة (Z01–Z06 أو كل المناطق) وعدد أيام من 1 لـ 15، وتعرف كل نوع شكوى هييجي منه كام. ده من خلال الدالة `get_forecast(zone, days)` في `forecast_api.py`، أو من ملف `outputs/zone_forecast_2026-01-01_to_15.csv` / `.json` (الجزء 6).
**لأي موقع:** اقرا ملفات الـ CSV/JSON أو استدعي `get_forecast`، ومتشغّلش الموديل جوه الموقع.

</div>

---

## 1. What the model does

- **Target:** the daily count of citizen complaints for each of the **15 complaint types** (`category_id`).
- **Input:** the last **30 days** of daily counts, plus calendar facts known in advance (weekday, Fri/Sat weekend, public holiday).
- **Output:** a forecast for each of the **next 15 days**, with an 80% range (`low_80`–`high_80`).
- **Model:** LightGBM with `objective="poisson"` (counts are non-negative integers): 400 trees, learning rate 0.03, 15 leaves. One global model covers all 15 types, with `category_id` as a categorical feature.
- **Training window:** cutoffs from 30 Jul to 16 Dec 2025. July is the start because complaint volume doubled after the app launched in June, so earlier months describe a different city.
- **Final forecast:** cutoff 31 Dec 2025, covering 1–15 Jan 2026.

## 2. Folder contents

| Path | What it is |
|---|---|
| `04_Complaints_Forecast.ipynb` | The notebook, already executed with all outputs (bilingual explanations). |
| `04_Complaints_Forecast.html` | The same notebook as a web page. Open it in any browser, no Python needed. |
| `data/req_prepared.parquet` | Complaints, one row per complaint (copied from `oasis_mob_pss/data_clean`). |
| `data/calendar.parquet` | 2025 calendar with the team's holiday flags (copied from `oasis_mob_pss/data_clean`). |
| `outputs/forecast_2026-01-01_to_15.csv` | **The city forecast** per type per day, 225 rows. |
| `outputs/forecast_15day_totals.csv` | 15-day total per type (1–15 Jan) with an 80% range, plus a `TOTAL` row for the whole city. |
| `outputs/december_backtest.csv` | December test predictions vs actuals, for every method. |
| `model/lightgbm_complaints_forecast.txt` | **The trained model weights:** every tree of the final LightGBM model, in LightGBM's native text format. |
| `model/model_card.json` | What is needed to use the weights: feature order, category order, parameters, cutoffs, holidays and library versions. |
| `model/load_and_predict.py` | A standalone script that loads the weights and writes a 15-day forecast for any cutoff, without retraining. It reproduces `outputs/forecast_2026-01-01_to_15.csv` exactly. |
| `outputs/zone_forecast_2026-01-01_to_15.csv` / `.json` | **The zone forecast:** zone × type × day (6 × 15 × 15 = 1,350 rows). |
| `outputs/zone_accuracy_by_days.csv` | Accuracy, MAE and coverage per method, level and zone, for every number of days from 1 to 15 (Nov–Dec tests). |
| `outputs/zone_backtest.csv` | Zone test predictions vs actuals (4 tests × 3 methods × 1,350 rows). |
| `forecast_api.py` | `get_forecast(zone, days)`: reads the two zone CSVs and returns the answer, with no model needed. |
| `model/lightgbm_zone_forecast.txt` | Weights of the LightGBM-zone model (the alternative zone method). |
| `model/model_card_zone.json` | Zone model card: features, zone and type order, parameters, and which method produced the zone CSV. |
| `model/load_and_predict_zone.py` | Rebuilds the zone forecast from the saved weights. It reproduces `outputs/zone_forecast_2026-01-01_to_15.csv` exactly. |
| `MODEL_REPORT.md` | A full description of everything done: data, features, methods, tests, results, tuning, the noise ceiling, limitations and a changelog. |
| `requirements.txt` | Exact pinned versions for the notebook. |
| `requirements-chronos.txt` | Optional: torch and chronos-forecasting, only for the Chronos comparison. |

**Data path:** the notebook first looks in `./data/`. If `req_prepared.parquet` is not there, it falls back to `../oasis_mob_pss/data_clean/`, so the folder works both on its own and when placed next to `oasis_mob_pss`.

## 3. How to run

Tested on Windows 11 with Python 3.13.1; any Python 3.10+ should work. Run these commands from inside the `forecast` folder:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt

# optional, only for the Chronos comparison (~200 MB torch CPU + ~200 MB model download on first run)
.venv\Scripts\python.exe -m pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python.exe -m pip install -r requirements-chronos.txt

# run (the working directory must be the forecast folder)
.venv\Scripts\jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=1800 04_Complaints_Forecast.ipynb
.venv\Scripts\jupyter nbconvert --to html 04_Complaints_Forecast.ipynb
```

On macOS/Linux, use `.venv/bin/python` and `.venv/bin/jupyter`. A run takes about 1 minute without Chronos and a few minutes with it. If torch or chronos is not installed, the Chronos cell prints `Chronos skipped: ...` and the rest of the notebook still runs.

**Note for chronos-forecasting 2.x:** the argument of `predict_quantiles` was renamed from `context` to `inputs`, so the notebook passes it positionally (`chronos.predict_quantiles(context, ...)`). Keep it that way.

## 4. Results (December test)

The model never sees December during training. Each test gives it the 30 days before a cutoff and compares its 15-day forecast with what actually happened.

- **Test 1:** cutoff 30 Nov, forecasting 1–15 Dec; training cutoffs up to 15 Nov.
- **Test 2:** cutoff 16 Dec, forecasting 17–31 Dec; the model is retrained with training cutoffs up to 1 Dec.

**Metrics:**
- **MAE:** mean absolute error, in complaints per type per day.
- **Accuracy:** 100% − WAPE, where WAPE = Σ|error| / Σ actual.
- **Range coverage:** the share of days where the actual count fell inside the 80% range.

**Overall (both tests):**

| Method | MAE | Accuracy | Range coverage |
|---|---|---|---|
| Baseline (mean of the same weekday over the last 4 weeks) | 2.88 | 74.74% | – |
| **LightGBM (chosen)** | **2.66** | **76.65%** | 83.78% |
| Chronos-Bolt-Small (pretrained, zero-shot) | 2.80 | 75.44% | 88.67% |

**Per test:**

| Test | Baseline | LightGBM | Chronos-Bolt |
|---|---|---|---|
| Test 1 (1–15 Dec) | 2.74 / 76.14% | **2.51 / 78.15%** | 2.68 / 76.66% |
| Test 2 (17–31 Dec) | 3.01 / 73.31% | **2.81 / 75.12%** | 2.91 / 74.19% |

**Accuracy at aggregate levels** (same December predictions, summed before scoring; section 9 of the notebook):

| Level | Baseline | LightGBM | Chronos-Bolt |
|---|---|---|---|
| Each type, each day (the table above) | 74.7% | 76.7% | 75.4% |
| Each type, 15-day total | 92.5% | 93.1% | 92.6% |
| Whole city, each day | 94.0% | 93.9% | 90.4% |

### Why ~77% and not 90%: the noise ceiling

Daily counts behave like Poisson draws. A type averaging 10 complaints a day naturally swings by about ±3 from day to day, even when nothing changes. A *perfect* model that knew the true daily rate would still score only about **76.6%** on this data. That figure is the expected Poisson absolute error at LightGBM's predicted rates. LightGBM is therefore at the ceiling.

A tuning sweep of 72 settings (learning rate 0.01/0.03/0.1 × leaves 7/15/31/63 × trees 200/400/1000 × poisson/l1) confirmed this. The best setting reached 77.02% (0.03, 7 leaves, 200 trees, poisson), a gain of only +0.4 points. Bigger models fell to about 74% because they overfit the noise. The notebook keeps the original settings.

**Why LightGBM:** it won both tests, uses the calendar (weekday, weekend, holidays) that Chronos cannot see, trains in seconds on a laptop CPU, and is explainable through feature importance (section 12 of the notebook).

## 5. Output contract (for integration)

### `outputs/forecast_2026-01-01_to_15.csv`

UTF-8, comma-separated, 225 rows (15 dates × 15 types) plus a header row.

| Column | Type | Meaning |
|---|---|---|
| `date` | `YYYY-MM-DD` | Forecast day (2026-01-01 … 2026-01-15) |
| `category_id` | string | Complaint type (one of the 15 below) |
| `pillar` | string | Sector of that type (fixed mapping below) |
| `forecast` | float, 1 decimal | Expected number of complaints that day |
| `low_80` | int | Lower end of the 80% range (Poisson 10th percentile) |
| `high_80` | int | Upper end of the 80% range (Poisson 90th percentile) |
| `model` | string | Free-text description of the model, the same on every row |

**The 15 `category_id` values and their `pillar`** (exact strings):

| category_id | pillar |
|---|---|
| `app` | `citizen_services` |
| `hvac` | `buildings` |
| `power_outage` | `energy` |
| `noise` | `environment` |
| `parks` | `environment` |
| `parking` | `mobility` |
| `roads` | `mobility` |
| `traffic_signals` | `mobility` |
| `safety` | `public_safety` |
| `streetlights` | `public_safety` |
| `cleanliness` | `waste` |
| `waste_overflow` | `waste` |
| `sewer` | `water` |
| `water_leak` | `water` |
| `water_outage` | `water` |

The existing dashboard's `MOB` and `PSS` pillars correspond to `mobility` and `public_safety`.

### `outputs/forecast_15day_totals.csv`

16 rows: one per `category_id`, sorted from the highest total down, plus a final row with `category_id = TOTAL` and `pillar = all` for the whole city.

| Column | Type | Meaning |
|---|---|---|
| `category_id` | string | Complaint type, or `TOTAL` |
| `pillar` | string | Sector (same mapping as above), or `all` |
| `forecast_15d` | int | Expected complaints over 1–15 Jan (the sum of the daily forecasts) |
| `low_80` | int | Lower end of the 80% range (Poisson 10th percentile of the summed rate) |
| `high_80` | int | Upper end of the 80% range (Poisson 90th percentile of the summed rate) |

The 15-day ranges cover day-to-day Poisson noise only, not model error, so treat them as a minimum spread. December accuracy at this level is about 93%.

Use this file for "15-day total per type" figures instead of summing `forecast_2026-01-01_to_15.csv`.

### `outputs/december_backtest.csv`

One row per (test, method, cutoff, date, type): 450 rows per method, so 900 rows without Chronos and 1,350 with it.

| Column | Meaning |
|---|---|
| `cutoff` | Last day of data the forecast was allowed to see |
| `date` | Forecast day |
| `h` | Horizon in days after the cutoff (1–15) |
| `category_id` | Complaint type |
| `pred` | Predicted count |
| `method` | `Baseline`, `LightGBM` or `Chronos-Bolt` |
| `actual` | Real count that day |
| `exam` | `Exam 1 (1–15 Dec)` or `Exam 2 (17–31 Dec)` |
| `low`, `high` | 80% range (empty for the Baseline) |
| `abs_err` | \|pred − actual\| |

## 6. Zone-level forecast and get_forecast

**For any website or dashboard:** don't run the model inside the site. Either read the ready files (`outputs/*.csv` or `outputs/*.json`), or call `get_forecast(zone, days)` from `forecast_api.py`. Refresh the files by re-running the notebook (section 7).

### What it answers

Pick a **zone** (`"Z01"` … `"Z06"`, or `"ALL"`) and a **number of days** (any whole number from 1 to 15). It returns how many complaints of each type are expected in that zone over those days, day by day, with the total and the accuracy of that choice.

```python
from forecast_api import get_forecast          # run from the forecast folder (or add it to sys.path)

r = get_forecast("Z01", days=5)
r["by_type"]     # category_id, pillar, forecast (sum over the days), low_80, high_80; most complaints first
r["daily"]       # type × date table
r["total"]       # {"forecast": 223.8, "low_80": 205, "high_80": 243}
r["accuracy"]    # {"accuracy_%": 81.75, "mae": 2.89, "coverage_%": 85.0, ...} from the Nov–Dec tests

r = get_forecast("ALL", days=7)
r["by_zone"]     # zone totals, most complaints first (Z01 316.9, Z05 303.1, Z02 294.5, Z04 116.6, Z06 83.8, Z03 31.3)
r["zone_type"]   # zone × type table
```

Invalid input raises `ValueError`: an unknown zone, or days outside 1–15 or not a whole number. The function needs pandas, numpy and scipy only.

### Zone method and accuracy

There are 6 zones × 15 types = 90 series, averaging about 1.8 complaints per series per day. Three methods were tested on 4 tests (cutoffs 31 Oct, 15 Nov, 30 Nov and 16 Dec 2025):

- **Baseline:** the same weekday over the last 4 weeks.
- **LightGBM-zone:** one Poisson model with zone and city features, using the city model's settings.
- **Top-down (chosen):** the city LightGBM forecast per type × the zone's share of that type over the last 60 days.

Top-down had the best average zone × type accuracy over N = 1..15: 76.72%, against 76.35% for LightGBM-zone and 74.88% for the Baseline.

**Accuracy % when choosing N days** (the sum of the first N days, all 4 tests):

| Level | Method | 1 | 3 | 5 | 7 | 10 | 15 |
|---|---|---|---|---|---|---|---|
| zone × type | Baseline | 43.4 | 67.3 | 74.5 | 78.6 | 80.7 | 83.2 |
| zone × type | LightGBM-zone | 45.7 | 68.6 | 75.7 | 79.4 | 81.9 | 84.4 |
| zone × type | **Top-down** | **46.2** | 67.9 | **76.3** | **79.6** | **82.4** | **85.0** |
| zone total | Baseline | 85.7 | 91.9 | 93.7 | 94.2 | 95.6 | 95.7 |
| zone total | LightGBM-zone | 83.7 | 90.8 | 93.1 | 93.6 | 95.6 | 95.8 |
| zone total | Top-down | 83.9 | 90.8 | 92.6 | 93.2 | 95.2 | 95.6 |

**Per zone (Top-down, zone × type):**

| Zone | Complaints/day | 1 day | 7 days | 15 days |
|---|---|---|---|---|
| Z01 | 45.0 | 50.4 | 82.9 | 86.5 |
| Z02 | 41.3 | 59.6 | 81.9 | 87.1 |
| Z05 | 43.6 | 56.2 | 82.0 | 86.9 |
| Z04 | 16.5 | 6.3 | 73.0 | 81.6 |
| Z06 | 11.5 | 3.9 | 70.4 | 78.4 |
| Z03 | 4.6 | −43.0 | 50.4 | 61.1 |

Accuracy is 100 − WAPE, so it goes **negative** when the total error is larger than the total actual complaints. That happens for the tiny zone Z03 over 1 day. Small zones should be shown over 7–15 days. Every value is in `outputs/zone_accuracy_by_days.csv`.

### Data contract

**`outputs/zone_forecast_2026-01-01_to_15.csv`** (and the same records in `.json`, as an array of objects): 1,350 rows, sorted by zone, day_number and category_id.

| Column | Type | Meaning |
|---|---|---|
| `zone` | string | `Z01` … `Z06` |
| `date` | `YYYY-MM-DD` | Forecast day |
| `day_number` | int 1–15 | Days after the cutoff (31 Dec 2025). Filter `day_number <= N` for "next N days". |
| `category_id` | string | One of the 15 types (section 5) |
| `pillar` | string | Sector of the type (section 5) |
| `forecast` | float, 2 decimals | Expected complaints that day in that zone |
| `low_80`, `high_80` | int | 80% range for that day (Poisson 10th and 90th percentiles) |
| `model` | string | The method that produced the forecast (`Top-down`) |

For a multi-day total, sum `forecast` and recompute the range as `poisson.ppf(0.1 / 0.9, sum)`. Do not sum `low_80` and `high_80`. `get_forecast` already does this.

**`outputs/zone_accuracy_by_days.csv`:** 405 rows.

| Column | Meaning |
|---|---|
| `method` | `Baseline`, `LightGBM-zone` or `Top-down` |
| `level` | `zone x type`, `zone total` or `city x type` |
| `zone` | `ALL` (pooled), or `Z01` … `Z06` (only for `zone x type`) |
| `days` | N, from 1 to 15 |
| `accuracy` | 100 − WAPE of the N-day sums |
| `mae` | Mean absolute error of the N-day sums |
| `coverage` | % of N-day sums inside the 80% range |

**`outputs/zone_backtest.csv`:** 16,200 rows (4 tests × 3 methods × 1,350). Columns: `cutoff, date, h, zone_id, category_id, actual, method, exam, pred, abs_err`.

### Zone January totals (1–15 Jan 2026, Top-down)

| Zone | Expected complaints |
|---|---|
| Z01 | 690 |
| Z05 | 660 |
| Z02 | 642 |
| Z04 | 254 |
| Z06 | 182 |
| Z03 | 68 |
| **All** | **2,496** |

The zones add up to the city forecast.

## 7. How to refresh the forecast

1. Update `data/req_prepared.parquet` (and `calendar.parquet` for new holidays) with the new days.
2. In the notebook:
   - extend `all_days` to the new last date;
   - in section 13, move the last training cutoff to (last date − 15 days) and the forecast cutoff `make_examples(...)` to the last date;
   - add new public holidays to `HOLIDAYS`.
3. Re-run the notebook (the command in section 3). It rewrites the city and zone CSV/JSON files and the zone accuracy file. If the dates change, update the file names in `forecast_api.py` (`FORECAST_FILE`) and anywhere a site reads them. For the zone part, also move `ZONE_CUTOFF` and the `"2025-12-16"` in section 19, and the test cutoffs in `ZEXAMS` (section 17).

Retrain at least monthly. Once a full post-launch year exists, add Ramadan and seasonal flags.

## 8. Link with the BERT complaint classifier

The forecast counts complaints **per `category_id`**. Any complaint classified by the BERT model must use **exactly the same 15 `category_id` strings** listed in section 5. Otherwise its complaints won't be counted in the right series when the forecast is retrained. If BERT uses different labels, map them to these 15 names before the data reaches `req_prepared.parquet`.

## 9. Limitations

- **The data is synthetic.** The results prove the method works, not that the model is ready for a real city.
- **The training period is short** (Jul–Nov/Dec 2025): only 3 public holidays (23 Jul, 4 Sep, 6 Oct) and **no Ramadan**, so holiday and seasonal effects are weakly learned. 7 Jan 2026 (Coptic Christmas) was added as a holiday using the team's 2025 calendar rule.
- **Low-volume types are less accurate:** `app`, `hvac` and `traffic_signals` (~5–7 per day) score about 65–69%. The randomness is proportionally larger for small counts.
- **Accuracy per type per day is capped near ~77%** by Poisson noise (section 4). Report aggregate accuracies (~93–94%) for planning-level decisions.
