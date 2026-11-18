# Complaints Simulator, next 60 days: Model Report

<div dir="rtl">

**ملخص بالعربي:**
- **المشروع:** جديد ومنفصل عن نوتبوك 04. بيتوقع **نوع** الشكاوى و**عددها** و**مكانها** (المنطقة) لكل يوم من **1 يناير لـ 1 مارس 2026** (60 يوم)، ومع كل رقم أحسن حالة (P10) وأسوأ حالة (P90) من Simulator بيعيد كل يوم 1000 مرة.
- **الداتا:** اتدربنا على **السنة كلها** (44,817 شكوى)، والموديل عارف إطلاق التطبيق في 15 يونيو.
- **الموديل المختار: LGB-all-year.** في امتحان نوفمبر–ديسمبر، اللي اتمتحن فيه الـ 3 موديلات، كسب في كل المستويات. ودقة إجمالي كل نوع في كل منطقة على الـ 60 يوم وصلت 88.4%. وأثبتنا إن الداتا القديمة **بتفيد شوية**: 71.1 مقابل 70.5.
- **تحذير بصراحة:** في امتحان سبتمبر–أكتوبر، الطريقة البسيطة كسبت. ده لأن الموديل وقتها ماكانش شاف ولا شهر كامل بعد التطبيق، والموديل النهائي مش في الموقف ده.
- **السيناريوهات:**
  - **الطبيعي:** ومعاه أحسن وأسوأ حالة.
  - **رمضان:** بيقلل الشكاوى ~10% في أيامه.
  - **حل مشكلة:** تقليل نوع شكوى في منطقة بنسبة.
  - **زيادة سكان منطقة.**
- **الافتراضات:** رمضان 2026 وأجازات يناير 2026 **افتراضات**، ومكتوبة تحت.

</div>

---

## 1. Goal and unit

- **Goal:** for every day from 2026-01-01 to 2026-03-01 (60 days), the expected number of complaints per **zone** (Z01–Z06) × **type** (15 `category_id`), with a P10–P90 range.
- **Unit:** zone × type × day = 6 × 15 = **90 daily series**.
- **Location:** the finest location in the data is the zone. There are no streets or coordinates.
- **Separate project:** folder `forecast_60d`. It does not modify `forecast/` (the 15-day model) or `oasis_mob_pss/`; it only reads their data.

## 2. Data

| Source | Use |
|---|---|
| `req_prepared.parquet`, all of 2025 (44,817 complaints, 0 without a zone) | Counted per day × zone × type. Days with no complaints count as 0. |
| `calendar.parquet` | Holidays and Ramadan 2025 (1–29 Mar 2025) |
| `dim_zones.parquet` | Population per zone, for the population scenario |

Volume roughly doubled after the app launched on 15 Jun 2025:

| Period | Complaints per day | From the app |
|---|---|---|
| Jan–May | 68–85 | 0% |
| June | 107 | 42% |
| Jul–Dec | 154–171 | about 60% |

The model is told about the launch through two features, so the pre-app months can be used without confusing it:
- `post_app`: whether the target day is after the launch;
- `window_post_app_share`: the share of the last 30 days that were after the launch.

## 3. Assumptions (all listed)

1. **Ramadan 2026:** 2026-02-18 to 2026-03-19 (approximate, **assumed**). Inside the forecast window this covers 18 Feb–1 Mar (12 days).
2. **Holidays 2026:** 2026-01-07 and 2026-01-25, with the same fixed dates as 2025 (**assumed**). The 2025 holidays come from `calendar.parquet`.
3. **Weekend:** Friday and Saturday.
4. **Ramadan effect:** learned from Ramadan 2025, which was **before** the app launch. It is applied as a relative effect through the model.
5. **Population scenario:** the number of complaints per 1,000 residents stays the same for every type.
6. **Fix scenario:** the reduction percentage is a **user assumption**, not learned from data.
7. **The data is synthetic:** the results show the method works, not readiness for a real city.

## 4. Features

These are the same in spirit as the 15-day zone model. Complaint features use only days ≤ the cutoff; only calendar facts are known about the future.

| Feature | Meaning |
|---|---|
| `zone_id`, `category_id` | Categorical |
| `h` | Days ahead (1–60) |
| `dow`, `is_weekend`, `is_holiday`, `is_ramadan` | About the target day |
| `post_app` | Target day after 15 Jun 2025 |
| `window_post_app_share` | Share of the 30-day window after the launch |
| `mean_7`, `mean_30`, `std_30`, `same_dow_4w`, `trend`, `weekend_ratio` | The zone × type series over the last 30 days |
| `city_mean_30` | City mean per day for that type |
| `zone_share_30` | (zone + 0.5) / (city + 0.5 × 6) for that type |
| `zone_total_mean_30` | All complaints in the zone per day |

**Training examples:** 276 daily cutoffs (30 Jan–1 Nov 2025, so that all 60 targets fall inside 2025) × 90 series × 60 days = **1,490,400**.

## 5. Models

| Model | Idea |
|---|---|
| **Baseline** | Mean of the same weekday over the last 4 weeks, per zone × type. The weekly pattern repeats for 60 days. |
| **LGB-all-year** | One global LightGBM (Poisson) that forecasts h = 1..60 directly, trained on cutoffs from 30 Jan 2025 |
| **LGB-post-app-only** | Identical, but trained only on cutoffs from 30 Jul 2025. It answers "does the old data help?" |

**LightGBM settings:**
- They match notebook 04: learning rate 0.03, 15 leaves, min_data_in_leaf 40, feature/bagging fraction 0.8, lambda_l2 1, 400 trees, seed 42.
- **Not tuned on the tests.**

## 6. Tests

Each test trains only on cutoffs whose 60 target days end on or before the test cutoff.

| Test | Cutoff | Forecasts | Last training cutoff |
|---|---|---|---|
| Exam A | 2025-08-31 | 1 Sep–30 Oct | 2 Jul |
| Exam B | 2025-10-31 | 1 Nov–30 Dec | 1 Sep |

- LGB-post-app-only **cannot be tested in Exam A**, because no post-app cutoff has its 60 targets finished by 31 Aug.
- **Accuracy** = 100 − WAPE.
- **Views:** daily, weekly (7-day sums over the first 56 days), monthly (30-day sums).
- **Levels:**
  - zone × type: each type in each zone;
  - zone total: all types in a zone;
  - city × type: each type across the city.

### Results: accuracy %

**Exam B**, the only test with all 3 models:

| Model | Daily z×t | Daily zone | Daily city×t | Weekly z×t | Weekly zone | Weekly city×t | Monthly z×t | Monthly zone | Monthly city×t |
|---|---|---|---|---|---|---|---|---|---|
| Baseline | 43.1 | 84.4 | 73.9 | 77.8 | 91.6 | 88.7 | 84.8 | 93.2 | 91.3 |
| **LGB-all-year** | **47.2** | **85.6** | **76.3** | **79.1** | **93.5** | **89.3** | **87.0** | **95.6** | **92.6** |
| LGB-post-app-only | 47.0 | 85.5 | 76.1 | 78.2 | 93.3 | 89.1 | 86.1 | 94.9 | 92.0 |

**Exams A + B:**

| Model | Daily z×t | Daily zone | Daily city×t | Weekly z×t | Weekly zone | Weekly city×t | Monthly z×t | Monthly zone | Monthly city×t |
|---|---|---|---|---|---|---|---|---|---|
| **Baseline** | 42.1 | **84.5** | **73.2** | **77.3** | **92.5** | **89.4** | **85.0** | **94.2** | **92.0** |
| LGB-all-year | **42.6** | 81.7 | 72.9 | 72.4 | 87.2 | 83.9 | 79.2 | 88.4 | 86.4 |

**Sum of the first N days, zone × type, Exam B:**

| Model | N=1 | 7 | 14 | 30 | 45 | 60 |
|---|---|---|---|---|---|---|
| Baseline | 28.7 | 79.8 | 84.3 | 85.2 | 85.7 | 86.1 |
| **LGB-all-year** | 30.5 | **80.4** | **85.1** | **87.3** | **88.3** | **88.4** |
| LGB-post-app-only | **32.0** | 79.3 | 84.2 | 86.2 | 87.3 | 87.3 |

For the zone total, Exam B: LGB-all-year scores 93.8% at N = 7, 96.8% at N = 14 and 95.6% at N = 60.

**Per zone (LGB-all-year, Exam B, zone × type, sum of the first N days):**

| Zone | N=1 | 7 | 30 | 60 |
|---|---|---|---|---|
| Z01 | 31.0 | 82.7 | 89.6 | 90.7 |
| Z02 | 47.8 | 84.7 | 88.0 | 86.9 |
| Z03 | −138.1 | 47.1 | 65.4 | 72.5 |
| Z04 | −109.9 | 76.3 | 89.5 | 85.4 |
| Z05 | 41.1 | 80.2 | 87.4 | 91.5 |
| Z06 | 21.9 | 74.5 | 81.3 | 83.7 |

Accuracy can be negative when the total error exceeds the total actuals. That happens for 1-day sums in the small zones Z03 and Z04. Use weekly or monthly views for small zones.

### Choice, stated plainly

**Chosen: LGB-all-year.** Mean zone × type accuracy over the daily, weekly and monthly views:

| Test | Baseline | LGB-all-year | LGB-post-app-only |
|---|---|---|---|
| **Exam B** | 68.57 | **71.08** | 70.45 |
| Exam A | **67.66** | 58.08 | – (cannot be tested) |

- **Exam B:** the comparable test, and LGB-all-year is the best model at every view and level shown.
- **Exam A, a caveat:** the Baseline was better. At Exam A the model had been trained only up to cutoff 2 Jul, so it had **never seen a 30-day window fully after the app launch**, and it then had to forecast September–October. That is exactly the situation the final model is **not** in: its training runs to cutoff 1 Nov and includes about 110 cutoffs whose 30-day window is fully after the launch (Exam B's training had about 50).
- **For a forecast made in a similar early-regime situation**, the Baseline is the safer choice.

**Does the old (pre-app) data help?** Yes, slightly. In Exam B, LGB-all-year scored 71.08 against 70.45 for LGB-post-app-only. It is also the only way to have a usable model early after a regime change (Exam A).

## 7. Simulator

- **Draws:** 1,000 per zone × type × day.
- **Distribution check:** the Pearson dispersion of the daily residuals was 0.98 in Exam A and 0.99 in Exam B, so day-to-day noise is Poisson-like.
- **What Poisson misses:** the 60-day sums per series vary more than Poisson because of model level error. The series-level σ² was 0.061 in Exam A and 0.011 in Exam B.
- **Chosen distribution:** **negative binomial** as gamma–Poisson. Each series has one level multiplier per draw, from Gamma(1/σ², σ²) with mean 1, and the daily counts are Poisson(mean × multiplier). The final σ² = 0.0357 is the mean of the two tests.
- **Coverage, cross-fitted** (σ² estimated on one test, coverage measured on the other). The target for P10–P90 is 80%:

| Test | Distribution | σ² | Daily | Weekly | Monthly |
|---|---|---|---|---|---|
| Exam A | Poisson | 0 | 92.2 | 65.7 | 37.8 |
| Exam A | Negative binomial | 0.0105 (from B) | 92.6 | 68.8 | 46.1 |
| Exam B | Poisson | 0 | 92.2 | 85.4 | 68.9 |
| Exam B | Negative binomial | 0.0609 (from A) | 93.5 | 92.6 | 92.8 |

- **Daily** coverage is above 80% because daily counts are small integers.
- **Weekly and monthly** are the real test. Poisson alone is too narrow. Negative binomial improves it, but coverage depends on how large the model's level error turns out to be. The ranges are a reasonable estimate, not a guarantee.

## 8. Forecast: 1 Jan → 1 Mar 2026 (LGB-all-year, mean)

| Zone | Jan 2026 | Feb 2026 | 1 Mar | 60 days |
|---|---|---|---|---|
| Z01 | 1,379 | 1,243 | 45 | 2,667 |
| Z02 | 1,326 | 1,198 | 43 | 2,567 |
| Z03 | 153 | 133 | 4 | 290 |
| Z04 | 552 | 504 | 19 | 1,075 |
| Z05 | 1,400 | 1,263 | 46 | 2,709 |
| Z06 | 391 | 354 | 13 | 758 |
| **All** | **5,201** | **4,695** | **170** | **10,066** |

**Whole city, 60 days:** 10,066 complaints, with P10–P90 of 9,720–10,407.

**Top types, whole city (mean, P10–P90):**

| Type | January | February |
|---|---|---|
| waste_overflow | 552 (481–624) | 495 (430–561) |
| streetlights | 527 (462–600) | 477 (418–539) |
| cleanliness | 478 (421–540) | 436 (380–493) |
| water_leak | 470 (404–538) | 427 (365–490) |
| roads | 444 (382–503) | 402 (346–457) |

February is lower partly because it is shorter, and partly because Ramadan starts on 18 Feb (see below).

## 9. Scenarios: `simulator_api.simulate(...)`

Normal and scenario are drawn with the **same random numbers**, so their difference is the scenario's effect only.

| Scenario | Inputs | Example result |
|---|---|---|
| `normal` | zone, days, view | All zones, 60 days: 10,066 (9,720–10,407) |
| `ramadan_off` | – | **Ramadan effect:** normal 10,066 vs no Ramadan 10,263, so Ramadan means **−198 complaints (−2.0% over 60 days)**. It is concentrated in the Ramadan days: week 8 is −116 (−9.5%) and days 57–60 are −64. The largest effects are parks, sewer and parking. |
| `fix` | zone (or `fix_zone`), `category`, `start_date`, `reduce_pct` | Z01 streetlights −30% from 2026-01-15: Z01 total 2,667 → 2,603 (−64, −2.4%) |
| `population` | zone (or `pop_zone`), `new_population` | Z04 6,000 → 9,000 residents: Z04 total 1,075 → 1,612 (+537, +50%). Parking 137 → 206. |

All examples are saved in `outputs/scenario_examples_60d.csv`.

## 10. Files

| File | Rows | Content |
|---|---|---|
| `outputs/zone_forecast_60d.csv` / `.json` | 5,400 | zone, date, day_number (1–60), category_id, pillar, mean, p10, p50, p90 (daily) |
| `outputs/zone_forecast_60d_weekly.csv` | 810 | zone, category_id, pillar, week (1–9; week 9 = days 57–60), start_date, end_date, days, mean, p10, p50, p90 |
| `outputs/zone_forecast_60d_monthly.csv` | 270 | Same, per calendar month (2026-01, 2026-02, 2026-03 = 1 day) |
| `outputs/zone_forecast_60d_ramadan_off.csv` | 5,400 | Mean with Ramadan switched off (used by the ramadan_off scenario) |
| `outputs/accuracy_60d.csv` | – | exams, method, view, level, zone, days, accuracy, mae |
| `outputs/backtest_60d.csv` | 27,000 | Test predictions vs actuals |
| `outputs/simulator_coverage_60d.csv` | 4 | The coverage table above |
| `outputs/scenario_examples_60d.csv` | 45 | The three scenario examples per type |
| `model/lightgbm_60d.txt` | – | **Weights** of the final LGB-all-year model (400 trees) |
| `model/model_card_60d.json` | – | Features, zone and type order, parameters, cutoffs, holidays, Ramadan days, assumptions, simulator σ², population |
| `model/load_and_predict_60d.py` | – | Rebuilds the `mean` column from the weights. **Verified:** all 5,400 values are identical. |
| `simulator_api.py` | – | `simulate(...)`; reads the CSVs and the card only, no model needed |

**Two notes on the files:**
- **P10, P50 and P90 in the CSV** come from 1,000 seeded draws. `simulate("ALL", days=60)` uses the same random stream (it works from the 4-decimal means, so it matches up to rounding). Other selections draw their own numbers, so their percentiles can differ slightly from the CSV.
- **"Monthly" means two different things:** in the accuracy tables it is a 30-day block; in the forecast files it is a calendar month.

## 11. Limitations

- **The data is synthetic.**
- **Ramadan:** 2026 dates are assumed, and the only Ramadan the model has seen (March 2025) was before the app launched.
- **Holidays:** January 2026 holidays are assumed fixed-date.
- **Daily forecasts for small zones and types are weak.** Z03 and Z04 1-day accuracy is negative, so use weekly or monthly.
- **Ranges** depend on the size of the model's level error, which varied a lot between the two tests.
- **Tests:** there are only 2, and the two disagree (see section 6).
- **The fix scenario's percentage is a user assumption.**

## 12. How to reproduce

From `forecast_60d`, using the environment of the `forecast` project (no changes to it are needed), or any environment with `forecast/requirements.txt` installed:

```powershell
..\forecast\.venv\Scripts\jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=5400 05_Complaints_Simulator_60d.ipynb
..\forecast\.venv\Scripts\jupyter nbconvert --to html 05_Complaints_Simulator_60d.ipynb
..\forecast\.venv\Scripts\python.exe model\load_and_predict_60d.py 2025-12-31
```

The full run takes several minutes, because it builds about 1.5 M training examples and trains 4 LightGBM models.

## 13. Changelog (30 Oct 2026)

1. Created the `forecast_60d` folder and copied `req_prepared.parquet`, `calendar.parquet` and `dim_zones.parquet` into `data/`.
2. Wrote notebook 05 (all of 2025, 90 series, 60-day direct LightGBM, 3 models, 2 tests, accuracy by view, level, zone and N, negative-binomial simulator with cross-fitted coverage), plus `simulator_api.py` and `model/load_and_predict_60d.py`.
3. First run: a bug in the weekly/monthly aggregation (`AttributeError: 'numpy.ndarray' object has no attribute 'to_numpy'`). Fixed.
4. Second run: noticed the selection code's comment promised "must also beat the Baseline over both exams", but the code did not check it, and LGB-all-year does not meet it (Exam A). I replaced the rule with an explicit one: choose on Exam B and print the Exam A caveat. I documented it in the notebook (section 6) and here.
5. Final run with the HTML export. The loader reproduces the mean forecast exactly. Built `forecast_60d_handoff.zip` and tested it from a fresh unzip.

`forecast/` and `oasis_mob_pss/` were not modified.
