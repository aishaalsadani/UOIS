# Complaints Forecast — Model Report

<div dir="rtl">

**ملخص بالعربي:**
- **الهدف:** نتوقع عدد الشكاوى لكل نوع من الـ 15 نوع، لكل يوم من الـ 15 يوم الجايين، من آخر 30 يوم.
- **المقارنة:** قارنّا 3 طرق على امتحانين في ديسمبر: الطريقة البسيطة (Baseline)، وLightGBM، وChronos من Amazon.
- **الفايز:** LightGBM فاز في الامتحانين، بدقة 76.7% لكل نوع في كل يوم (MAE ‏2.66 شكوى). وده قريب من أقصى دقة ممكنة (~77%) بسبب العشوائية الطبيعية في الأرقام.
- **على مستوى الإجمالي:** الدقة 93.1% لإجمالي كل نوع على الـ 15 يوم، و93.9% لإجمالي المدينة اليومي.
- **الضبط:** جرّبنا 72 إعداد مختلف، وأحسنهم زوّد 0.4% بس.
- **التوقع:** إجمالي 1–15 يناير 2026 حوالي 2,496 شكوى.
- **الأوزان:** موجودة في `model/lightgbm_complaints_forecast.txt`.
- **جديد، المناطق:** تختار منطقة (Z01–Z06 أو الكل) وعدد أيام من 1 لـ 15 بـ `get_forecast`. اتمتحنّا 4 مرات (نوفمبر وديسمبر)، وأحسن طريقة كانت Top-down (توقع المدينة × نسبة المنطقة).
  - دقة المنطقة × النوع: 46% ليوم واحد، و80% لـ 7 أيام، و85% لـ 15 يوم.
  - دقة إجمالي المنطقة: 84–96%.
  - المنطقة Z03 صغيرة جدًا، ودقتها ضعيفة لو الأيام قليلة.

</div>

---

## 1. Goal

Forecast the **daily number of citizen complaints for each of the 15 complaint types** for the **next 15 days**, using the last **30 days** of history plus calendar facts that are known in advance. The output feeds the dashboard and the 3D city: expected count per type per day, with an 80% range.

## 2. Data

| Source | Use |
|---|---|
| `req_prepared.parquet` (44,817 complaints, 1 Jan–31 Dec 2025) | Counted per day × `category_id`. A day with no complaints of a type is a **0**, not a missing row. |
| `calendar.parquet` | Public-holiday flags (the team's assumed calendar, DQ-06). |

- **The data is synthetic** (a training dataset).
- **Training starts on 1 Jul 2025.** The app launched in June 2025 and daily volume roughly doubled (DQ-10), so earlier months describe a different city.
- **Weekend** = Friday and Saturday.
- **Holidays in the training period:** 23 Jul, 4 Sep and 6 Oct 2025. 7 Jan 2026 (Coptic Christmas) was added using the same team calendar rule.
- **Average daily volume per type** (Jul–Dec): from 18.1 (`waste_overflow`) down to 5.0 (`app`).

## 3. Features (inputs to LightGBM)

One training example = (cutoff day, complaint type, horizon h = 1..15). Everything about past complaints comes from the 30 days **up to and including the cutoff** only.

| Feature | Meaning |
|---|---|
| `category_id` | Complaint type (categorical, 15 levels, fixed order) |
| `h` | Days ahead of the cutoff (1–15) |
| `dow` | Weekday of the target day (0 = Mon) |
| `is_weekend` | Target day is Friday or Saturday |
| `is_holiday` | Target day is a public holiday |
| `mean_7` | Mean daily count over the last 7 days |
| `mean_30` | Mean daily count over the last 30 days |
| `std_30` | Standard deviation over the last 30 days (how noisy the type is) |
| `same_dow_4w` | Mean count on the same weekday over the last 4 weeks (only days ≤ cutoff) |
| `trend` | (mean_7 + 0.5) / (mean_30 + 0.5): rising or falling |
| `weekend_ratio` | (weekend mean + 0.5) / (weekday mean + 0.5) within the 30-day window: this type's weekend effect |

Target `y` = the actual count on the target day.

## 4. Training design and leakage rule

- **Sliding window, one day at a time.** The first cutoff is 30 Jul (the first full 30-day window). Every following day is another cutoff.
- **Leakage rule:** when forecasting day h, the model never sees any complaint after the cutoff, even days between the cutoff and the target. Only calendar facts about the target day are allowed.
- **Test 1 training set:** cutoffs from 30 Jul to 15 Nov, so every target day falls inside November. That is 109 cutoffs × 15 types × 15 horizons = **24,525 examples**.
- **One global model** covers all 15 types, which share patterns through `category_id`.

## 5. Methods compared

| # | Method | Idea | Why included |
|---|---|---|---|
| 1 | **Baseline** | Mean of the same weekday over the last 4 weeks | The bar to beat. A model that can't beat it is useless. No trained weights. |
| 2 | **LightGBM (chosen)** | Gradient-boosted trees, `objective="poisson"` | Counts are small non-negative integers, so Poisson is the right loss. It also uses the calendar and is fast and explainable. |
| 3 | **Chronos-Bolt-Small** | Amazon's pretrained time-series model (~48M params), zero-shot | Tests whether a large pretrained model beats a small local one. We have no weights of our own for it: it downloads `amazon/chronos-bolt-small` from Hugging Face. |

**LightGBM parameters:**

| Parameter | Value |
|---|---|
| learning_rate | 0.03 |
| num_leaves | 15 |
| min_data_in_leaf | 40 |
| feature_fraction | 0.8 |
| bagging_fraction | 0.8 (bagging_freq 1) |
| lambda_l2 | 1.0 |
| Trees | 400 |
| seed | 42 |

**80% range:**
- LightGBM: Poisson 10th–90th percentile of the predicted mean.
- Chronos: its own 0.1 and 0.9 quantiles.
- Baseline: no range.

## 6. Evaluation: two December tests

December was never used for training in the tests.

| Test | Cutoff | Forecasts | LightGBM trained on cutoffs up to |
|---|---|---|---|
| Test 1 | 30 Nov | 1–15 Dec | 15 Nov |
| Test 2 | 16 Dec | 17–31 Dec | 1 Dec (retrained, as would happen each month) |

**Metrics:**
- **MAE:** mean absolute error, in complaints per type per day.
- **Accuracy:** 100% − WAPE, where WAPE = Σ|error| / Σ actual.
- **Range coverage:** % of days where the actual count fell inside the 80% range (target ≈ 80%).
- **RMSE** and **R²** are reported as extras.

## 7. Results

**Overall (both tests, 450 type-days per method):**

| Method | MAE | Accuracy | Range coverage | RMSE | R² |
|---|---|---|---|---|---|
| Baseline | 2.88 | 74.74% | – | 3.65 | 0.56 |
| **LightGBM** | **2.66** | **76.65%** | 83.78% | **3.38** | **0.62** |
| Chronos-Bolt | 2.80 | 75.44% | 88.67% | 3.54 | 0.59 |

**Per test (MAE / accuracy):**

| Test | Baseline | LightGBM | Chronos-Bolt |
|---|---|---|---|
| Test 1 (1–15 Dec) | 2.74 / 76.14% | **2.51 / 78.15%** | 2.68 / 76.66% |
| Test 2 (17–31 Dec) | 3.01 / 73.31% | **2.81 / 75.12%** | 2.91 / 74.19% |

LightGBM won **both** tests.

**Accuracy per type** (both tests; ordered by volume):

| Type | Avg/day | Baseline | LightGBM | Chronos |
|---|---|---|---|---|
| waste_overflow | 18.1 | 79.8 | 82.0 | 80.4 |
| streetlights | 16.5 | 79.9 | 83.9 | 80.3 |
| cleanliness | 14.9 | 79.9 | 82.3 | 81.4 |
| water_leak | 14.6 | 78.7 | 79.1 | 80.9 |
| roads | 13.7 | 71.3 | 72.6 | 71.9 |
| parking | 13.3 | 75.4 | 75.6 | 73.3 |
| noise | 11.5 | 67.8 | 72.7 | 74.7 |
| water_outage | 10.2 | 70.1 | 73.9 | 70.8 |
| power_outage | 8.5 | 71.3 | 77.1 | 77.2 |
| safety | 8.3 | 75.5 | 77.6 | 76.2 |
| sewer | 8.2 | 77.4 | 70.5 | 67.9 |
| traffic_signals | 6.9 | 64.6 | 68.6 | 66.1 |
| hvac | 6.4 | 64.1 | 65.6 | 63.6 |
| parks | 6.4 | 74.9 | 76.8 | 74.9 |
| app | 5.0 | 66.9 | 66.5 | 67.2 |

**Accuracy at aggregate levels** (same predictions, summed before scoring):

| Level | Baseline | LightGBM | Chronos |
|---|---|---|---|
| Each type, each day | 74.7% | 76.7% | 75.4% |
| Each type, 15-day total | 92.5% | 93.1% | 92.6% |
| Whole city, each day | 94.0% | 93.9% | 90.4% |

The following levels were computed outside the notebook for discussion only:

| Level | Baseline | LightGBM | Chronos |
|---|---|---|---|
| Sector (8) × day | 82.3% | 83.9% | 82.5% |
| Each type × 3-day block | 85.0% | 86.6% | 85.5% |
| Each type × week | 89.8% | 90.5% | 89.8% |

## 8. Hyperparameter search

A grid of **72 LightGBM settings** was scored on the same two December tests:

| Setting | Values tried |
|---|---|
| learning_rate | 0.01, 0.03, 0.1 |
| num_leaves | 7, 15, 31, 63 |
| Trees | 200, 400, 1000 |
| objective | poisson, l1 |

| Result | Settings | Accuracy | MAE |
|---|---|---|---|
| Current | 0.03 / 15 / 400 / poisson | 76.65% | 2.66 |
| Best | 0.03 / 7 / 200 / poisson | 77.02% | 2.62 |
| Worst | (several) | 73.7–74.3% | – |

- The gain from tuning is only +0.4 points, and the best setting was picked on the test itself, so even that is optimistic.
- **Bigger models are worse:** more leaves or a learning rate of 0.1 overfit the day-to-day noise.
- **Decision:** keep the original settings.

## 9. Why ~77% is the ceiling (noise analysis)

- **Poisson noise ceiling.** If daily counts are Poisson with the true rate μ, even a perfect model that knows μ has an expected absolute error of E|Y − μ|. At LightGBM's predicted rates, that perfect model would score **≈ 76.6%** accuracy per type per day. LightGBM (76.65%) is at that ceiling.
- **Residuals carry no pattern.** The mean lag-1 autocorrelation of LightGBM's December residuals, within each (test, type) series, is **−0.05**, which is ≈ 0. Yesterday's error does not predict today's, so no model can learn anything more from these series.
- **Why totals score higher.** Summing over days or types cancels independent noise, so totals reach 93–94% with the same model.

## 10. Precision and recall

- **Precision and recall don't apply directly.** They are classification metrics, and this is a regression or count-forecasting problem. The right metrics are MAE, WAPE-based accuracy and range coverage. Precision and recall belong to the BERT complaint classifier.
- **"Busy day" experiment.** For illustration, a day was called *busy* for a type when its count was above that type's 80th percentile in Jul–Nov. December had 106 busy days out of 450 (24%).

**Alert when the point forecast crosses the threshold:**

| Method | Precision | Recall |
|---|---|---|
| Baseline | 28.6% | 18.9% |
| Chronos | 31.2% | 4.7% |
| LightGBM | 0% | 0% (7 alerts, all false) |

**Alert when the upper end of the 80% range crosses the threshold:**

| Method | Precision | Recall | Days flagged |
|---|---|---|---|
| LightGBM | 29.0% | 89.6% | 328 of 450 |
| Chronos | 24.3% | 100% | 436 of 450 |

**Conclusion:** single busy days are random spikes. Every method is near the 24% chance rate, consistent with the noise ceiling. These numbers are not recommended for the presentation.

## 11. January 2026 forecast

- **Final model:** trained on cutoffs from 30 Jul to 16 Dec 2025.
- **Forecast cutoff:** 31 Dec 2025, covering 1–15 Jan 2026.
- **Daily city total:** about 179 on weekdays and about 133–138 on Fri/Sat. 7 Jan (holiday) drops to 157.

**15-day totals per type (80% range):**

| Type | Pillar | Expected | Range |
|---|---|---|---|
| waste_overflow | waste | 269 | 248–290 |
| streetlights | public_safety | 257 | 237–278 |
| water_leak | water | 230 | 211–250 |
| cleanliness | waste | 222 | 203–241 |
| parking | mobility | 204 | 186–223 |
| roads | mobility | 204 | 186–222 |
| noise | environment | 172 | 156–189 |
| water_outage | water | 154 | 138–170 |
| safety | public_safety | 143 | 128–158 |
| sewer | water | 136 | 121–151 |
| power_outage | energy | 131 | 116–145 |
| parks | environment | 108 | 95–122 |
| traffic_signals | mobility | 108 | 95–121 |
| app | citizen_services | 81 | 69–92 |
| hvac | buildings | 76 | 65–88 |
| **Whole city** | all | **2,496** | 2,432–2,560 |

The 15-day ranges cover Poisson noise only, not model error, so treat them as a minimum spread.

## 11b. Zone-level forecast (Part 2 of the notebook, sections 15–22)

**Goal:** choose a zone (Z01–Z06 or ALL) and a number of days N (1–15). The system returns the expected complaints per type in that zone, day by day, with the total and the accuracy of that choice.

**Data:**
- `zone_id` from `req_prepared.parquet`. No rows are missing a zone.
- 6 zones × 15 types = 90 daily series, which add up exactly to the city counts.
- Volume is very uneven:

| Zone | Complaints/day (Jul–Dec) | Share of city |
|---|---|---|
| Z01 | 45.0 | 27.7% |
| Z05 | 43.6 | 26.8% |
| Z02 | 41.3 | 25.4% |
| Z04 | 16.5 | 10.2% |
| Z06 | 11.5 | 7.1% |
| Z03 | 4.6 | 2.8% |

- The average series has about 1.8 complaints per day.

**Methods.** All three use the same leakage rule: features only use days ≤ the cutoff.

1. **Baseline:** the same weekday over the last 4 weeks, per zone × type.
2. **LightGBM-zone:** one global Poisson model with the city model's settings, not tuned on the tests.
   - Features: `zone_id`, `category_id`, `h`, `dow`, `is_weekend`, `is_holiday`, then `mean_7`, `mean_30`, `std_30`, `same_dow_4w`, `trend` and `weekend_ratio` of the zone × type series.
   - Hierarchy features: `city_mean_7`, `city_mean_30`, `zone_share_30` = (zone + 0.5) / (city + 0.5 × 6), and `zone_total_mean_30`.
   - 140 training cutoffs × 90 series × 15 = 189,000 examples in total.
3. **Top-down:** the city LightGBM forecast per type × the zone's share of that type over the last 60 days ≤ cutoff.

**Tests:** 4 tests over two months. Each trains only on cutoffs up to (test cutoff − 15 days).

| Test | Cutoff | Forecasts | Last training cutoff |
|---|---|---|---|
| Nov A | 31 Oct | 1–15 Nov | 16 Oct |
| Nov B | 15 Nov | 16–30 Nov | 31 Oct |
| Dec A | 30 Nov | 1–15 Dec | 15 Nov |
| Dec B | 16 Dec | 17–31 Dec | 1 Dec |

**Scoring for "N days":** sum the first N forecast days and the first N actual days per group, then compute accuracy = 100 − WAPE, MAE, and 80%-range coverage (Poisson percentiles of the summed mean). This is repeated for every N from 1 to 15, pooled over the 4 tests.

**Accuracy % (pooled over the 4 tests):**

| Level | Method | N=1 | 3 | 5 | 7 | 10 | 15 |
|---|---|---|---|---|---|---|---|
| zone × type | Baseline | 43.4 | 67.3 | 74.5 | 78.6 | 80.7 | 83.2 |
| zone × type | LightGBM-zone | 45.7 | 68.6 | 75.7 | 79.4 | 81.9 | 84.4 |
| zone × type | **Top-down** | **46.2** | 67.9 | **76.3** | **79.6** | **82.4** | **85.0** |
| zone total | Baseline | 85.7 | 91.9 | 93.7 | 94.2 | 95.6 | 95.7 |
| zone total | LightGBM-zone | 83.7 | 90.8 | 93.1 | 93.6 | 95.6 | 95.8 |
| zone total | Top-down | 83.9 | 90.8 | 92.6 | 93.2 | 95.2 | 95.6 |
| city × type | Baseline | 72.4 | 84.2 | 87.6 | 89.7 | 90.1 | 92.0 |
| city × type | LightGBM-zone | 73.7 | 85.3 | 87.5 | 89.8 | 90.3 | 92.4 |
| city × type | Top-down | 74.4 | 85.5 | 87.6 | 89.8 | 91.0 | 92.7 |

**Choice:**

| Method | Mean zone × type accuracy over N = 1..15 |
|---|---|
| **Top-down (chosen)** | **76.72%** |
| LightGBM-zone | 76.35% |
| Baseline | 74.88% |

- **Top-down is used for the zone forecast.** It wins zone × type at 5 of the 6 N values shown (N = 3 goes to LightGBM-zone). Per test it is not always first: for example, at N = 7 the Baseline is slightly ahead in Dec A (81.9 vs 81.7) and LightGBM-zone in Nov B.
- **The margin over LightGBM-zone is small** (0.4 points), so either would be defensible. Top-down is also simpler: it reuses the city model and adds no new weights.
- **For the zone total, the Baseline is slightly better at short N** (85.7% vs 83.9% at N = 1). All methods are about 95.6% at N = 15.

**80% range coverage (zone × type, Top-down):** 95% at N = 1, 84–88% at N = 3–7, and 79% at N = 15. Close to the 80% target over longer windows.

**Per zone (Top-down, zone × type):**

| Zone | N=1 | 3 | 5 | 7 | 10 | 15 |
|---|---|---|---|---|---|---|
| Z01 | 50.4 | 74.9 | 81.8 | 82.9 | 84.0 | 86.5 |
| Z02 | 59.6 | 71.3 | 79.1 | 81.9 | 84.7 | 87.1 |
| Z03 | −43.0 | 26.3 | 34.6 | 50.4 | 54.0 | 61.1 |
| Z04 | 6.3 | 48.8 | 65.0 | 73.0 | 79.6 | 81.6 |
| Z05 | 56.2 | 74.2 | 79.9 | 82.0 | 84.6 | 86.9 |
| Z06 | 3.9 | 47.4 | 63.3 | 70.4 | 74.7 | 78.4 |

- **Negative accuracy** means the total error exceeded the total actuals. That happens for Z03, which averages about 0.3 complaints per type per day.
- **Small zones should be presented over 7–15 days.**
- **Per test (zone × type, Top-down):** N = 1 ranged 30.8–57.9%, N = 7 ranged 77.1–81.7%, and N = 15 ranged 84.1–85.9%.

**January forecast (cutoff 31 Dec 2025, Top-down, 15-day totals):**

| Zone | Expected complaints |
|---|---|
| Z01 | 690 |
| Z05 | 660 |
| Z02 | 642 |
| Z04 | 254 |
| Z06 | 182 |
| Z03 | 68 |
| **All** | **2,496** |

The zones add up to the city forecast (2,496.1 vs 2,496.3, rounding). The largest zone × type cells are:
- Z01: water_leak 81, streetlights 77, waste_overflow 69.
- Z05: waste_overflow 76, parking 71, noise 61.
- Z02: water_leak 76, streetlights 69, waste_overflow 69.

**Selection API:** `forecast_api.get_forecast(zone, days)` reads `zone_forecast_*.csv` and `zone_accuracy_by_days.csv` and returns:
- `by_type`: each type with its 80% range;
- `daily`: type × day;
- `total`;
- `accuracy`: for that zone and N;
- for `"ALL"`, also `by_zone` and `zone_type`.

It validates its inputs. Examples:

| Call | Total (80% range) | Accuracy |
|---|---|---|
| `get_forecast("Z01", 5)` | 223.8 (205–243) | 81.75% |
| `get_forecast("Z03", 15)` | 68.0 (58–79) | 61.09% |
| `get_forecast("ALL", 7)` | 1,146.1 (1,103–1,190) | zone × type 79.6%, zone total 93.18% |

## 12. Model weights

| File | Content |
|---|---|
| `model/lightgbm_complaints_forecast.txt` | **The trained weights:** every tree of the final LightGBM model in LightGBM's native text format. Load it with `lgb.Booster(model_file=...)`. |
| `model/model_card.json` | Feature order, the 15 categories in code order, pillar mapping, parameters, number of trees, training cutoff range, window and horizon, holidays, weekend days and library versions. |
| `model/load_and_predict.py` | A standalone script: it loads the weights, rebuilds the features from `data/` for any cutoff and writes a 15-day forecast CSV. |

| `model/lightgbm_zone_forecast.txt` | Weights of the LightGBM-zone model (trained on cutoffs 30 Jul–16 Dec), the alternative zone method. |
| `model/model_card_zone.json` | Zone features, zone and type order, parameters, holidays, and `forecast_method` (Top-down) with its city-model and 60-day share settings. |
| `model/load_and_predict_zone.py` | Rebuilds the zone forecast from the saved weights. Top-down uses the city weights plus the shares from `data/`. It reproduces `outputs/zone_forecast_2026-01-01_to_15.csv` exactly (verified: 1,350 rows identical). |

- **Using the weights:** `category_id` must be a `pandas.Categorical` with exactly the category order in `model_card.json`. The model's output is the expected count (Poisson mean).
- **Baseline:** a formula, so it has no weights.
- **Chronos:** pretrained by Amazon. Nothing was trained, so there are no weights of ours.

## 13. Output files

| File | Rows | Columns |
|---|---|---|
| `outputs/forecast_2026-01-01_to_15.csv` | 225 | date, category_id, pillar, forecast, low_80, high_80, model |
| `outputs/forecast_15day_totals.csv` | 16 | category_id (or TOTAL), pillar (or all), forecast_15d, low_80, high_80 |
| `outputs/december_backtest.csv` | 1,350 | cutoff, date, h, category_id, pred, method, actual, exam, low, high, abs_err |
| `outputs/zone_forecast_2026-01-01_to_15.csv` / `.json` | 1,350 | zone, date, day_number, category_id, pillar, forecast, low_80, high_80, model |
| `outputs/zone_accuracy_by_days.csv` | 405 | method, level, zone, days, accuracy, mae, coverage |
| `outputs/zone_backtest.csv` | 16,200 | cutoff, date, h, zone_id, category_id, actual, method, exam, pred, abs_err |

`HANDOFF_README.md` has the full column definitions and the dashboard integration guide.

## 14. How to reproduce

Run these from the `forecast` folder:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
# optional Chronos:
.venv\Scripts\python.exe -m pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python.exe -m pip install -r requirements-chronos.txt

.venv\Scripts\jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=1800 04_Complaints_Forecast.ipynb
.venv\Scripts\jupyter nbconvert --to html 04_Complaints_Forecast.ipynb

# forecast from the saved weights only (no retraining):
.venv\Scripts\python.exe model\load_and_predict.py 2025-12-31
```

**Environment used:**
- Windows 11 and Python 3.13.1
- pandas 3.1.0, pyarrow 26.0.0, numpy 2.5.4, scipy 1.18.1, matplotlib 3.11.2
- lightgbm 4.7.0
- jupyter 1.1.1, nbconvert 7.17.2, ipykernel 7.4.0
- Optional: torch 2.15.0+cpu and chronos-forecasting 2.3.2

**Chronos API fix:** chronos-forecasting 2.x renamed the first argument of `predict_quantiles` from `context` to `inputs`. The keyword call failed with:

`TypeError: ChronosBoltPipeline.predict_quantiles() missing 1 required positional argument: 'inputs'`

The notebook now passes the context positionally, which works with both 1.x and 2.x.

## 15. Limitations

- **The data is synthetic.** The results prove the method works, not readiness for a real city.
- **The training history is short.** About 5 months after launch, with only 3 holidays and **no Ramadan**, so holiday and seasonal effects are weakly learned. The model needs a full post-launch year.
- **Low-volume types are weaker:** `app`, `hvac` and `traffic_signals` score about 65–69%.
- **Per-type daily accuracy is capped near 77%** by Poisson noise. Use the aggregate levels for planning.
- **The 80% ranges ignore model uncertainty.** Coverage was still 83.8% in December, slightly above target.
- **The BERT classifier link:** its labels must use exactly the same 15 `category_id` strings, or the forecast series will be wrong.

## 16. Changelog (29 Oct 2026, in order)

1. Created `forecast\.venv` (Python 3.13.1) and installed pandas, pyarrow, numpy, scipy, matplotlib, lightgbm, jupyter, nbconvert and ipykernel.
2. Ran the notebook end to end. Baseline 2.88 / 74.74%, LightGBM 2.66 / 76.65%. Chronos was skipped because torch was missing (`ModuleNotFoundError No module named 'torch'`).
3. Installed torch 2.15.0+cpu and chronos-forecasting 2.3.2. The first Chronos run failed with the `predict_quantiles` TypeError, so I changed that one line to pass the context positionally. On the rerun Chronos-Bolt scored 2.80 / 75.44%.
4. Computed the Poisson noise ceiling (≈ 76.6%) and the aggregate accuracies (type 15-day total 93.1%, city daily 93.9%).
5. Ran a 72-setting LightGBM grid search. The best gain was +0.4 points and larger models overfit, so the settings are unchanged.
6. Made the data path portable (`./data` first, then `../oasis_mob_pss/data_clean`) and copied `req_prepared.parquet` and `calendar.parquet` into `forecast\data`.
7. Wrote `requirements.txt`, `requirements-chronos.txt` and `HANDOFF_README.md`, and built `forecast_handoff.zip`.
8. Ran the busy-day precision/recall experiment and the sector, 3-day and weekly accuracy levels. These live in scripts only, not in the notebook.
9. Added to the notebook the accuracy-by-level table (section 9) and the 15-day totals table, bar chart and `outputs/forecast_15day_totals.csv` (section 13). Re-ran it with identical results and built `forecast_handoff_v2.zip`. The first zip was locked by another program and left as it was.
10. Added the saving of model weights (`model/lightgbm_complaints_forecast.txt` and `model/model_card.json`), wrote `model/load_and_predict.py`, computed RMSE/R² and the residual autocorrelation, wrote this report and built `forecast_handoff_v3.zip`.

11. Zone level, notebook Part 2 (sections 15–22):
    - zone counts per zone × type × day;
    - three methods (Baseline, LightGBM-zone, Top-down) on 4 tests (Nov and Dec);
    - accuracy for every N = 1..15 (`zone_accuracy_by_days.csv`, `zone_backtest.csv`);
    - Top-down chosen (76.72% mean zone × type accuracy);
    - the January zone forecast (CSV and JSON);
    - `forecast_api.get_forecast(zone, days)`;
    - zone weights and card, and `load_and_predict_zone.py` (reproduces the zone CSV exactly).

    The dashboard code sketch was removed from `HANDOFF_README.md`. Re-ran the whole notebook: all city-level numbers unchanged. Built `forecast_handoff_v4.zip`.

`oasis_mob_pss` was never modified.
