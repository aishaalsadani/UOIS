# Model integration plan (Step 0: inventory, no code changed)

Prepared 31 Oct 2026. Synthetic data — for training only. **Nothing has been changed yet.** This plan waits for your OK on §6.

Files read:
- `citizen_app.py` (the Prompt 2 version, with `/api/health`, `/api/classify` and `/dashboard`);
- `Moamen/oasis_bert_model/bert/` (`config.json`, `model_info.json`, `oasis_franco.py`);
- `Moamen/bert code/Oasis_BERT_Notebook_READY2.ipynb`;
- `Ayat/PredectionModel/forecast_handoff_v4/forecast/`:
  - `HANDOFF_README.md`, `MODEL_REPORT.md` (outline);
  - `forecast_api.py`;
  - `model/load_and_predict.py`, `model/load_and_predict_zone.py`;
  - `model/model_card.json`, `model/model_card_zone.json`;
  - `requirements.txt`;
  - the `outputs/` listing;
- FINAL reports:
  - `reports/integration_notes.md`, `ml_readiness_report.md`, `sensor_warning_readiness_report.md`;
  - `evaluation/early_warning/detector_configuration_and_counts.csv`;
  - `evaluation/classifier/classifier_evaluation_summary.csv`;
- the `EarlyWarnings data/` folder listing.

**Where the dashboard is.** `oasis_city_system.html` is in `TheProject\`, one folder above `citizen_app.py`. `citizen_app.py` already looks there (`DASHBOARD_CANDIDATES`), and `/dashboard` served it in the Prompt 2 test. Nothing is missing. The file just isn't next to `citizen_app.py`.

---

## 1. Existing routes in `citizen_app.py`

| Method | Route | Model used | Mock / fallback today |
|---|---|---|---|
| GET | `/`, `/portal` | — (form page) | — |
| POST | `/submit` | BERT via `INFERENCE_ENGINE.predict` | **Silent keyword fallback** if BERT is not loaded. Since Prompt 2 the log record carries `engine` |
| GET | `/model-analytics` | reads the log | **Shows "Calibrated BERT Engine" when BERT is not loaded** (line 1585). A fallback result is labelled as BERT here |
| GET | `/batch`, `/template.csv`, `/export-batch` | — | — |
| POST | `/api/batch-upload` | BERT via `predict` per row | **Silent keyword fallback**, no engine field |
| POST | `/api/commit`, `/api/commit-batch` | — | writes `service_requests.csv` |
| POST | `/api/clear-analytics`, `/api/toggle-resolution` | — | rewrite the log |
| GET | `/api/forecast?zone=&days=` | **No model.** Reads `outputs/zone_forecast_2026-01-01_to_15.json` + `zone_accuracy_by_days.csv` | precomputed file, not a model call |
| GET | `/forecast`, `/dash` | — | serve `Output/dash_1.html` |
| GET | `/api/stats` | reads the log (last 20) | — |
| GET | `/dashboard`, `/api/health`, `/api/test-complaints` | — | added in Prompt 2 |
| POST | `/api/classify` | BERT only | refuses with `model_not_loaded`, never falls back (Prompt 2) |

The dashboard (`oasis_city_system.html`) gets model output in three ways:
- **Portal single and batch:** `/api/classify` (BERT only).
- **Model analytics tab:** `/api/stats`.
- **Forecast page and Early warning page:** **embedded copies of precomputed files**: Ayat's `OASIS_FORECAST_STORE` from `dash_1.html`, and Aya's `__DASH__.tab2` export. Neither calls a model.

## 2. The models

### 2.1 BERT complaint classifier (Moamen)

| Item | Value (source) |
|---|---|
| Base model | `UBC-NLP/MARBERTv2`, fine-tuned, 5 epochs (`model_info.json`) |
| Weights | `model.safetensors`, 326 MB, **saved in float16** (`config.json` `dtype: float16`; notebook `final_model.half()`) |
| Input | one text string (Arabic, Franco-Arabic or English) |
| Preprocessing | `text + " " + gloss(text)` with `oasis_franco.py` (`input_rule` in `model_info.json`). `citizen_app.preprocess_text` already does exactly this. The root copy of `oasis_franco.py` is byte-identical to the model folder's copy (same MD5) |
| Tokenizer | the saved `tokenizer.json`, `truncation=True`, `max_length=96` (training `MAX_LEN = 96`) |
| Output | softmax over **16 labels**: app, cleanliness, hvac, noise, parking, parks, power_outage, roads, safety, sewer, streetlights, traffic_signals, waste_overflow, water_leak, water_outage, water_pressure_low |
| Stored metrics | validation (template-grouped 15% split, 1,573 training texts): **macro-F1 0.9676, accuracy 0.9683**. Franco probe: Franco 0.8333, English 0.875 (`model_info.json`) |
| Test set | `Datasets/TestData/TestBert/oasis_bert_test_complaints_200.csv` with columns `zone_id, description_ar, expected_category` |

Note on PII masking:
- The app masks PII before classifying.
- Training texts were not masked; the kit swapped phone numbers into the templates.
- So the model sees `[تم حجب رقم الهاتف…]` where it trained on digits. See Q-7.

### 2.2 LightGBM complaints forecast (Ayat)

| Item | City model | Zone forecast |
|---|---|---|
| Weights | `lightgbm_complaints_forecast.txt` | **Top-down** (the method behind `outputs/zone_forecast_*.csv`, `model_card_zone.json` → `forecast_method`): city model × each zone's share of the type over the last 60 days. `lightgbm_zone_forecast.txt` is the alternative "LightGBM-zone" method |
| Code to reuse | `model/load_and_predict.py` (`make_examples`) | `model/load_and_predict_zone.py` (`city_examples`, Top-down block) |
| Raw input | `data/req_prepared.parquet` columns `date`, `category_id` (+ `zone_id` for zones); `date` parsed with `pd.to_datetime`, daily counts | same |
| Features, in order (`model_card.json`) | `category_id` (categorical, fixed order of 15), `h` (1–15), `dow` (0–6), `is_weekend` (Fri/Sat = dow 4, 5), `is_holiday` (20 dates in the card), `mean_7`, `mean_30`, `std_30`, `same_dow_4w`, `trend` = (m7+0.5)/(m30+0.5), `weekend_ratio` | city features + 60-day zone shares |
| Request parameters | **cutoff date** (`YYYY-MM-DD`); forecast = cutoff+1 … cutoff+15; needs 30 days of history ≤ cutoff | same; zones `Z01`–`Z06` |
| Output | per date × `category_id`: `forecast` (Poisson mean, 1 dp), `low_80` / `high_80` = `poisson.ppf(0.1/0.9, mean)` | per zone × date × type, 2 dp; multi-day totals re-ranged with `poisson.ppf` on the sum |
| Labels | 15 `category_id` (the BERT list without `water_pressure_low`) with a fixed pillar map | same + zone order Z01–Z06 |
| Stored metrics | December tests: MAE 2.66, accuracy 76.65%, range coverage 83.78% (README §4) | `outputs/zone_accuracy_by_days.csv` (405 rows: method × level × zone × days) |
| Reference outputs | `outputs/forecast_2026-01-01_to_15.csv` (225 rows), `forecast_15day_totals.csv` | `outputs/zone_forecast_2026-01-01_to_15.csv` (1,350 rows) |
| Libraries (card) | lightgbm 4.7.0, pandas 3.1.0, numpy 2.5.4, scipy 1.18.1, pyarrow 26.0.0 | same |

**Hard limit.** The data ends on 31 Dec 2025. A forecast can start on any day up to **2026-01-01**, the cutoff 31 Dec. Each start needs 30 days of history (zone Top-down: 60), so the earliest start is about early Feb 2025 (Mar 2025 for zones).

Earlier starts inside 2025 are back-tests on days the model may have trained on. The training cutoffs run from 30 Jul to 16 Dec 2025, and the model card warns that July is the first valid month.

### 2.3 Early warning

There is **no trained early-warning model**. Two rule outputs exist, both precomputed:

| Source | What it is | Files | Zone |
|---|---|---|---|
| **FINAL detector** | generic rule: same-slot past-28-day median/MAD, flag when \|robust z\| ≥ 6, district episodes, 3 tiers. The code is in `scripts/src/oasis_prep` (not read yet) | `evaluation/early_warning/tier1_event_matched_candidates.csv`, `tier2_unvalidated_anomalies.csv`, `tier3_data_quality_alerts.csv`, `evaluation/warning_evidence/warning_evidence_table.csv`, `warning_complaint_links.csv` | **district-level only.** The report says the sensor-to-zone mapping is unverified and contradicted by the 13 May event |
| **Aya's register** | 5 evidence levels, 409 replay records (what the EW page shows now) | embedded in `Output/dash_1.html` as `__DASH__.tab2` (no CSV of it in the folders) | carries a zone field taken from the unverified mapping |

The FINAL report's own verdict:
- "The generic detector is mostly reacting to distribution tails. It is not a usable early-warning signal as it stands."
- "No family has a validated detection rate."
- `90_ANSWER_KEYS_FOR_TESTING/test_planted_scenarios.csv` exists (283 bytes) but has not been read yet.

**Proposal:** a read-only `/api/early-warning` that filters the precomputed tables and returns the evidence. It runs no detection and is marked `"engine": "precomputed"`. Re-running the detector live would mean porting FINAL's pipeline, which is not a model and was not asked for. See Q-1.

## 3. Endpoints: model → endpoint → request → response → widget

| Model | Endpoint | Request | Response | Dashboard widget |
|---|---|---|---|---|
| — | `GET /api/health` | — | `{ok, models: {bert: {loaded, error, files, version, dtype, transformers, torch}, forecast_city: {loaded, error, file, lightgbm, card_versions}, forecast_zone: {...}, early_warning: {source, files, rows}}, dashboard_file}` | top-bar models chip (per-model dots), launcher report |
| BERT | `POST /api/classify` | `{"text": "..."}` (+ optional `"zone_id"`) | `{ok, category, confidence (%), top_k: [{category, confidence}], engine: "bert", latency_ms, masked_text, pii_detected, pillar}` (old keys `ranked` kept for compatibility) · 400 on empty or over-long text · 503 `{ok:false, reason:"model_not_loaded", error}` | Portal → Single report |
| BERT | `POST /api/classify/batch` | multipart CSV (`description_ar`, optional `zone_id`, `expected_category`) **or** `{"texts": [...]}` | `{ok, engine, n, results: [{row, category, confidence, top_k, masked_text, expected?}], summary: {by_category, mean_confidence, pii_masked, matched_expected?, accuracy?, macro_f1?}, latency_ms}` | Portal → Batch upload (replaces one call per row) |
| LightGBM city | `GET /api/forecast?start=YYYY-MM-DD&days=15` | `start` ≤ 2026-01-01, `days` 1–15 | `{ok, engine: "lightgbm", model_file, cutoff, start, days, daily: [{date, total, low_80, high_80}], by_type: [{category_id, pillar, forecast, low_80, high_80}], total: {forecast, low_80, high_80}, accuracy: {from: "model_card / README December tests", ...}, latency_ms}` | Forecast page: KPI cards, daily chart, category chart, table |
| LightGBM zone (Top-down) | `GET /api/forecast/zone?zone=Z01..Z06\|ALL&start=&days=` | as above + `zone` | `{ok, engine: "lightgbm-topdown", zone, daily, by_type, by_zone (ALL only), total, accuracy: zone_accuracy_by_days row, latency_ms}` | Forecast page: zone select, zone chart, KPI accuracy card |
| rule outputs | `GET /api/early-warning?zone=&from=&to=&source=final\|aya` | dates `YYYY-MM-DD`, zone optional | `{ok, engine: "precomputed", source, zone_status: "unverified", n, warnings: [{id, tier/level, family/pillar, start, end, peak_z, evidence, ...}], data_quality: [...]}` | Early warning page: register and tables |
| all | `GET /api/models/metrics` | — | `{bert: model_info.validation + tests, forecast: model_card + README §4 tables (from files), zone: zone_accuracy_by_days, classifier_eval: FINAL classifier_evaluation_summary.csv, early_warning: detector_configuration_and_counts.csv}` | Portal → Model analytics (stored metrics block) |

Every endpoint gets:
- input validation;
- 4xx JSON errors;
- CORS;
- one log file per model, appended per inference: `bert_inferences_log.json` (existing, plus `engine`, `latency_ms`, `source:"api"`), `forecast_inferences_log.json`, `early_warning_queries_log.json`.

Service layer (`models/`):
- `bert_service.py`, `forecast_service.py`, `early_warning_service.py`.
- Each loads once, behind a lock, with paths built from `citizen_app.py`'s folder via `pathlib`.
- `forecast_service.py` imports `make_examples` / `city_examples` logic **by copying the two scripts' functions verbatim into the service**. The scripts are written as top-level code that runs on import, so they can't be imported as they are.
- Existing routes keep working.

## 4. Verification planned (Step 4)

| Check | How | Compare with |
|---|---|---|
| BERT on 200 test complaints | `/api/classify/batch` on `oasis_bert_test_complaints_200.csv` → accuracy and macro-F1 vs `expected_category` | `model_info.json`: validation 0.9676 / 0.9683 (a different set, so not a like-for-like comparison) |
| Forecast city | `/api/forecast?start=2026-01-01&days=15` | `outputs/forecast_2026-01-01_to_15.csv`, every row, tolerance 0.05 |
| Forecast zone | `/api/forecast/zone?zone=ALL&start=2026-01-01&days=15` and each zone | `outputs/zone_forecast_2026-01-01_to_15.csv`, every row, tolerance 0.005 |
| Endpoints | `tests/test_api.py`, pytest + Flask test client, every endpoint incl. 4xx | — |
| Launcher | run `run_oasis.sh` here; you run `run_oasis.bat` | health report lists all models |

**BERT caveat.** The real `model.safetensors` (326 MB) has never reached this workspace; copying it from your computer timed out 3 times. I can build and test everything else here. The 200-complaint accuracy can only be measured either:
- on your computer: `python tests/eval_bert.py` prints accuracy and macro-F1, and I'll write that script; or
- here, if you attach `model.safetensors` (or a zip of the `bert` folder) to the chat.

## 5. Dependencies

The forecast needs `lightgbm`, `pandas`, `numpy`, `scipy` and `pyarrow` at runtime (to read the parquet files). `requirements.txt` has lightgbm, pandas and numpy as "optional for retraining"; it lacks scipy and pyarrow.

Proposal:
- move them to a required tier, with `scipy` and `pyarrow` added;
- minimum versions, not the card's exact pins: pandas 3.1.0 is newer than many installs, and the card's code uses only stable APIs;
- keep CPU-only torch;
- add `pytest` for the tests.

## 6. Questions before Step 1

1. **Early warning source.** Serve FINAL's precomputed tiers, Aya's 409-record register, or both via `source=`? Both are rule outputs, not models. The response says `engine: "precomputed"` and `zone_status: "unverified"`. Or should I skip `/api/early-warning` and list what is missing (labelled events, verified zone mapping, a family-specific rule) instead?
2. **Forecast `start` range.** Accept any start from the first date with 30 days of history up to 2026-01-01, flagging starts before 2026-01-01 as `"backtest": true`? Or only 2026-01-01? Nothing later is possible without new data.
3. **Existing `/api/forecast?zone=&days=`.** It reads the precomputed JSON today. Should it become the live city model (new `start` parameter), and should old callers that send `zone` be redirected to `/api/forecast/zone`? Or keep it as is and add `/api/forecast/city`?
4. **Offline pages.** Prompt 2 required the data pages to work offline. Plan: the Forecast and Early warning pages fetch the live API when the server answers. Otherwise they show the embedded store, with a badge "embedded copy · server offline" instead of "engine: LightGBM". OK, or API only?
5. **Logging `/api/classify`.** In Prompt 1 you asked for `/api/classify` to log nothing. This prompt asks to log every inference. Log API calls now (with `source:"api"`, so they are separate from `/submit` records)?
6. **Old fallback labels.** `/model-analytics` shows "Calibrated BERT Engine" when BERT is not loaded, and `/api/batch-upload` falls back silently. Fix both to say `engine: fallback` (two small edits to existing routes)?
7. **PII masking vs. training input.** Classify the masked text (privacy, current behaviour) or the raw text (matches training)? For the 200-row test I'd report both.
8. **BERT weights.** Will you run the evaluation script on your computer, or attach the model here?

Once these are answered: Step 1 (services) → Step 2 (API) → Step 3 (dashboard wiring, data only) → Step 4 (verification with numbers) → Step 5 (launcher, README). Every edited file gets a `.bak_before_integration` backup first.
