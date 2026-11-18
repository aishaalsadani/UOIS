# Decision Lab: plan (nothing changed yet)

Prepared 31 Oct 2026. Synthetic data — for training only. **Waiting for your OK on §7.**

Read for this plan:
- `citizen_app.py` (current, 133 KB) and `oasis_city_system.html` (Prompt 4 version, 8.1 MB);
- from Ayat's handoff: `HANDOFF_README_60d.md`, `simulator_api.py`, `model/model_card_60d.json`, `outputs/scenario_examples_60d.csv`, `outputs/accuracy_60d.csv`, `outputs/simulator_coverage_60d.csv`.

## 0. Checks already done (read-only, in my workspace)

| Check | Result |
|---|---|
| Handoff location | Not a zip: it is already unpacked as a folder at `TheProject\forecast_60d_handoff\forecast_60d\` (outer folder). I will **copy** it to `TheProject\TheProject\Ayat\PredectionModel\forecast_60d\`. The original stays where it is, and `forecast_handoff_v4\` is not touched |
| `simulate()` reproduces "Fix: Z01 streetlights −30% from 2026-01-15" | **Yes, exactly:** max difference 0.0 in all 8 columns × 15 categories against `scenario_examples_60d.csv`. Total: prevented 63.54 streetlight complaints (−2.38% of Z01's 2,666.92) |
| Speed of one `simulate()` fix run (1 zone, 60 days, 1,000 draws) | **about 4.2 s** in my workspace (2 CPU cores). Your PC is probably faster, but the leaderboard needs 90 runs: see §3 |
| Accuracy numbers you quoted | All in `outputs/accuracy_60d.csv` (exam "B only", LGB-all-year, zone × type): daily 47.17, weekly 79.05, monthly 87.02. The page will read them from the API, not type them |
| Population per zone | In `model_card_60d.json` (Z01 18,000 … Z06 4,000), served by the API |
| Ramadan and holidays on the time axis | From the model card: Ramadan 2026 = 18 Feb → 19 Mar (**marked "ASSUMED dates"** in the card); holidays 2026-01-07 and 2026-01-25 |
| BERT | Your `bert_test_report.txt`: BERT loaded, all 200 test complaints classified by BERT, **accuracy 0.9000, macro-F1 0.8985**. This work will not touch it |

## 1. Endpoints (new, read-only; existing routes unchanged)

| Method | Route | Request | Response |
|---|---|---|---|
| GET | `/api/simulate/meta` | — | zones, the 15 categories with their pillar, population per zone, horizon (60), first date, Ramadan dates (+ "assumed"), holidays in range, accuracy per view (from `accuracy_60d.csv`), P10–P90 coverage (from `simulator_coverage_60d.csv`) |
| POST | `/api/simulate` | `{zone, days, view, scenario, category, start_date, reduce_pct, new_population, fix_zone, pop_zone, include_detail}` | `simulate()` result as JSON: `by_type`, `by_period`, `by_zone`, `total`, `assumptions`, echo fields, plus `period_dates` (start/end date of every period, for the time axis) and `latency_ms`. DataFrames → records, NaN → null. `detail` (up to 5,400 rows) only when `include_detail: true`. `ValueError` → **400** `{ok: false, error: "<message from simulate>"}`. Bad JSON → 400 |
| GET | `/api/simulate/leaderboard?days=60&reduce_pct=30` | `days` ∈ {30, 60}, `reduce_pct` ∈ {10, 20, 30, 50} (other values → 400) | `{status: "ready", days, reduce_pct, start_date: "2026-01-01", runs: 90, top: [10 × {rank, zone, category_id, pillar, prevented, prevented_pct, normal_total, normal_p10, normal_p90, scenario_total, p10, p90}], computed_at, cached: true/false}`. While computing: `{status: "computing", done: n, total: 90}` with HTTP 202 |
| GET | `/api/health` | — | + `simulator_60d: {loaded, error, folder, forecast_file, rows, n_sims, leaderboard_cache: {...}}` |

- `prevented` = `normal_mean − mean` for the "all selected days" total of the fix zone × category, exactly as the formula you gave. `prevented_pct` = prevented ÷ normal_mean of that zone × category × 100.
- The P10–P90 ranges come from `simulate()`'s own draws. They are never summed across days.
- CORS on all of them, same as the other APIs. Every simulate call is logged to `simulator_queries_log.json` (request, latency, ok/error).

**Service layer:** a new `simulator_service.py` next to `citizen_app.py`.
- It loads `Ayat/PredectionModel/forecast_60d/simulator_api.py` with `importlib`. Ayat's code is not copied or changed, and no LightGBM is used.
- It builds every path from `citizen_app.py`'s folder, as `citizen_app.py` already does.
- It converts `simulate()` results to JSON and holds the leaderboard cache.

## 2. Page layout

New tab **Decision Lab**, between Overview and Pillars: `City map · Overview · Decision Lab · Pillars ▾ · Early warning · Forecast`. Same window bar style, card styles, light and dark tokens, Plotly theme and Noto Serif KR as the other pages.

```
┌ Decision Lab ─────────────────────────────────────────────────────────────┐
│ eyebrow: DECISION LAB · Ayat · 60-day complaints simulator (from 2026-01-01)│
│ title + one-line lede ("What if we fix one problem in one zone?")           │
├ 1. Best decisions ─────────────────────────────────────────────────────────┤
│ [Horizon: 30 | 60 days]  [Reduce: 10 | 20 | 30 | 50 %]   (computing 37/90…) │
│ #1 [PSS] Streetlights in Z01 → prevents ~NN complaints in 60 days (−30%)    │
│      without NN (P10–P90 a–b) · with NN (P10–P90 c–d)    [Try this decision]│
│ #2 …                                                         (10 rows)      │
├ 2. Time Machine ───────────────────────────────────────────────────────────┤
│ tabs: [Fix a problem] [Population change] [Ramadan effect]                  │
│ controls: zone · category · fix start date · reduce % slider · horizon      │
│           (30/60) · view (daily / WEEKLY / monthly)                         │
│ ⚠ daily view: "each type in each zone is only 47% accurate per day" (API)   │
│ impact cards: Without · With · Prevented (n, %) · Range P10–P90 (both)      │
│ chart: "without decision" line + P10–P90 band, "with decision" line + band, │
│        gap filled as "complaints prevented"; Ramadan (assumed) and holidays │
│        shaded on the time axis                                              │
│ assumptions (small text, from the API) · accuracy note for the chosen view  │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **Population change:** a slider for the zone's new population. It starts at the current population from the API, which is shown next to it.
- **Ramadan effect:** normal (Ramadan included) vs Ramadan switched off. The gap is labelled "Ramadan effect", not "prevented", because the sign can go either way: in Ayat's example, Ramadan off *adds* about 2%.
- **"Try this decision":** fills zone, category, reduce % and horizon from the row (start date 2026-01-01, as in the leaderboard), switches to the Fix tab, scrolls down and runs.
- **Overview card "Top 3 decisions":** placed after the KPI row. It shows rows #1–#3 of the default leaderboard (60 days, −30%), each opening Decision Lab with that decision loaded. While the cache is still being built it says "computing…"; offline it shows the usual "Models: offline — start run_oasis.bat".
- **City map:** the zone dossier (the panel that opens when you click a zone) gets a "Try a decision here" button. It opens the Time Machine for that zone, preset to that zone's best category from the leaderboard (or the first category if the leaderboard isn't ready).
- **Offline** (server not running, or the page opened as a file): Decision Lab shows the offline message. No numbers are embedded in the page; every number comes from the API.

## 3. Leaderboard speed (the one real constraint)

90 `simulate()` runs at about 4 s each is about 6 minutes in my workspace. On your PC it is probably 1–3 minutes, still far over 3 s. Plan:
1. **Disk cache.** Each (days, reduce %) result is saved to `cache/leaderboard_<days>_<pct>.json`, keyed by the forecast file's hash. Every call after the first, including after a restart, is read from disk in a few milliseconds. That meets "< 3 s after the first call".
2. **Warm start.** When the server starts, a background thread computes the default (60 days, −30%), so the Overview card is ready a minute or two after launch. The server answers everything else meanwhile.
3. **Parallel first run.** The 90 runs are spread over a process pool (CPU cores − 1). Same function, same seed, so the numbers are identical to a one-by-one run.
4. While a combination is being computed, the API returns HTTP 202 with progress. The page polls every 2 s and shows "computing 37/90".

The other 7 combinations (30/60 × 10/20/50 %) are computed the first time someone picks them, then cached.

## 4. Files

| File | Change | Backup first |
|---|---|---|
| `TheProject\Ayat\PredectionModel\forecast_60d\…` | **new**: copy of Ayat's folder (20 files, 8.1 MB) | — |
| `TheProject\simulator_service.py` | **new** | — |
| `TheProject\citizen_app.py` | 3 routes + `simulator_60d` in `/api/health` (Flask and the built-in fallback server). Nothing else changes | `citizen_app.py.bak_before_decision_lab` |
| `TheProject\run_oasis.bat`, `run_oasis.sh` | one model-report line: `Simulator 60d : LOADED / NOT loaded (reason)` | `*.bak_before_decision_lab` |
| `TheProject\requirements.txt` | add `scipy` to the forecast group (it is only there today as a scikit-learn dependency), and a new optional `tests` group with `pytest` | `requirements.txt.bak_before_decision_lab` |
| `TheProject\README.md` | new endpoints with curl examples | `README.md.bak_before_decision_lab` |
| `TheProject\tests\test_simulator_api.py` | **new**: pytest + Flask test client, covering: valid and invalid input on both endpoints; reproduction of the Fix example; leaderboard < 3 s on the second call | — |
| `oasis_city_system.html` | new tab and page, Overview card, City map dossier button. Built as a patch step, like Prompts 3 and 4; embedded data stays byte-identical | `oasis_city_system.before_decision_lab.html` |

## 5. What stays exactly as it is

- **BERT:** `/api/classify`, the portal and `/submit` are unchanged.
- **15-day forecast:** `/api/forecast` and `forecast_handoff_v4\` are unchanged.
- **All existing pages and routes:** unchanged.
- **Checks:**
  - before and after, I'll run the same route and page check as in the cleanup baseline and compare;
  - `test_bert.py` must still report 200 / 200 BERT.

## 6. Verification (after your OK)

1. Fix example reproduced through `POST /api/simulate` (not only the Python function).
2. pytest: both endpoints, valid and invalid input (bad zone, `days=61`, unknown category, `reduce_pct=150`, bad date, `population=0`, bad leaderboard parameters).
3. Leaderboard second call < 3 s (timed).
4. In the browser, light and dark, with screenshots, and no console errors in any step:
   - Decision Lab: "Try this decision" on 3 rows, population, Ramadan, daily warning;
   - Overview card;
   - City map dossier button.
5. `/api/health` and the launcher report show `simulator_60d`.
6. **On your PC:** run `run_oasis.bat`, then `.venv\Scripts\python.exe -m pytest tests -q`. Real timings come from there.

## 7. Questions before I start

1. **Leaderboard speed.** OK with §3: disk cache + warm-up at start + process pool, with a "computing…" state on the first call? The alternative is fewer draws for the leaderboard only (faster, but its numbers would differ slightly from the Time Machine's, so I don't recommend it).
2. **Copy, not move.** I'll copy the handoff into `Ayat\PredectionModel\forecast_60d\` and leave `TheProject\forecast_60d_handoff\` as it is. OK?
3. **pytest** isn't in `.venv` yet. May I add it to `requirements.txt` as an optional `tests` group? The launcher would install it on its next run (about 2 MB).
4. **Defaults.** Time Machine opens with zone Z01, the zone's top leaderboard category, start 2026-01-01, −30%, 60 days, weekly view. The leaderboard uses start 2026-01-01 as you specified. OK?
5. **Tab order:** `City map · Overview · Decision Lab · Pillars ▾ · Early warning · Forecast`. The top bar gets one tab wider. I'll re-check that the toggle, models chip and portal button stay visible at 1280–1920 px; the City map KPI strip gives way first, as now.
