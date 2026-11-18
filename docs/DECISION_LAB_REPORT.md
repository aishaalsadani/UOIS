# Decision Lab: report

31 Oct 2026 · synthetic data, for training only.

The plan is in `TheProject\DECISION_LAB_PLAN.md`. Nothing was retrained or deleted. No LightGBM runs in the website.

## 1. Fast path: what I chose

One `simulate()` call takes about 4.2 s here, so live updates and the leaderboard needed a faster way. The fast path in `simulator_service.py`:

- **Keeps the simulator's random numbers in memory.** For each zone and horizon it keeps the 1,000 random draws (same seed, same array shapes, same order as `simulate()`).
- **Re-draws only what a scenario changes:**
  - a fix re-draws 1 type in 1 zone from the start date on;
  - a population change re-draws that zone;
  - Ramadan-off is drawn once per zone and horizon, then reused.
- **Reuses `simulate()`'s own summary code.** The result is therefore **identical**, number for number, to Ayat's `simulate()`. This is checked on 39 cases (fix, population, Ramadan, normal × daily, weekly, monthly × single zones and the whole city × 17, 30 and 60 days).
- **Can fall back to the original.** Any request can still be answered by `simulate()` itself with `"engine": "reference"`.
- **Splits large re-draws over CPU cores, with threads.** The same function runs on the same numbers, so the result is identical. One core is always left free.
- **Caches results.** The server keeps the last 300 results, and the page keeps its own cache. A repeated setting answers in 0 ms.
- **Play.** `POST /api/simulate/frames` computes 11 real frames (0 → chosen %) in one call. The page fetches them about 1 s after each result, before you press ▶. It then animates between the frames.
- **One change from the approved plan: no process pool.** With the fast path, the full leaderboard (90 runs, all 1,000 draws) takes **19 s** on this 2-core workspace, against about 6 minutes before. A process pool would add memory and start-up cost for little gain. Disk cache, warm-up at start and the "computing x/90" state are in place as approved.

Timings on this 2-core workspace (your PC should be faster):

| Action | Time |
|---|---|
| Fix, after the zone's first request (`latency_ms` from the API) | 0.2–0.3 s |
| Same setting again | 0 ms (cached) |
| Population change | 1–2.6 s |
| Ramadan view, whole city | First time about 12 s here, so it is computed during the warm-up at server start |
| Leaderboard | First time 19 s (warm-up does 60 days / −30%). After that it is read from `cache\` in milliseconds, also after a restart. The pytest "< 3 s on the second call" check passes |

## 2. What is on the page

**New tab:** City map · Overview · **Decision Lab** · Pillars ▾ · Early warning · Forecast.

**1 · Best decisions**
- The top 10 of 90 runs, with a pillar tag and a "Try this decision" button on each row.
- Controls: horizon 30 / 60 days and reduce 10 / 20 / 30 / 50%.
- While a setting is computed for the first time, a progress bar shows "computing x/90".
- Rows slide in one by one. When a control changes, rows that stay in the top 10 glide to their new places and their numbers count to the new values.

**2 · Time Machine**
- Three tabs: Fix a problem / Population change / Ramadan effect.
- It updates by itself 400 ms after the last change. A slower answer cancels the one before it. While it computes, the old chart and cards stay visible under a shimmer; the screen is never blank.
- Chart:
  - "without" and "with" lines, each with its P10–P90 band;
  - the gap filled as "complaints prevented" (labelled "Ramadan effect" or "change" in the other tabs);
  - Ramadan (assumed dates) and the holidays marked on the date axis;
  - rich tooltips showing the period with its dates, without, with, prevented, and both P10–P90 ranges.
  - Note on the shorter last period: with 60 days, the last week has only 4 days. The axis title and the tooltip say so, because that week drops on the chart.
- Animation:
  - lines and bands move to new values in 450 ms;
  - the impact numbers count up or down.
  - With prefers-reduced-motion, values change without animation.
- Below the chart:
  - the simulator's own assumptions text;
  - the accuracy of the chosen view, with the P10–P90 coverage;
  - on the daily view, a warning: 47% per day for one type in one zone, against 79% weekly and 87% monthly. These numbers come from the API.
- **▶ Play:** runs the reduce % from 0 to your value so the gap grows on screen. Press again to stop.
- **"Try this decision":** fills the controls, scrolls smoothly to the Time Machine, flashes its border and runs.

**Defaults:** Z01, that zone's top leaderboard type (water leak), from 2026-01-01, −30%, 60 days, weekly.

**Overview:** a "Top 3 decisions" card. Each row opens that decision in the Decision Lab.

**City map:** a "Try a decision here →" button in the zone dossier. It opens the Time Machine for that zone with its best type.

**Offline:** if the server is not running, the page shows the usual "Models: offline — start run_oasis.bat" message, and no numbers. The models chip tooltip now also says whether the simulator is loaded.

## 3. Something you should know about the leaderboard

The fix starts on 1 Jan, the first forecast day, so "prevented" always comes out as exactly the chosen % of that type's forecast (−30% → 30.0%). The ranking is therefore really a ranking of **which zone × type has the most forecast complaints**. That is correct for the formula you gave, but it is worth saying when you present it. With a later start date in the Time Machine, the effect is smaller.

## 4. Verification

| Check | Result |
|---|---|
| "Fix: Z01 streetlights −30% from 2026-01-15" through `POST /api/simulate` | Identical to `scenario_examples_60d.csv` in all 8 columns × 15 types. Total 2,666.92 → 2,603.38, change −63.54 (−2.38%) |
| pytest `tests/test_simulator_api.py` | **26 passed**. Covers valid and invalid input on both endpoints, fast = reference, the Fix example, leaderboard < 3 s on the second call, meta, frames |
| Browser flow, dark and light (Playwright) | Covers: "Try this decision" on rows 1, 4 and 8; the slider; Play; the daily warning; population; Ramadan; the leaderboard at 30 days; the Overview card; the City map button. **No console errors** in either theme |
| Top bar at 1200 / 1280 / 1366 / 1440 / 1600 / 1920 px, both themes, City map and Decision Lab | 24 / 24: no overlap, portal button, chip and theme toggle all visible. Below 1440 px the tab padding is a little tighter to make room |
| Every route, BERT `/api/classify`, the 15-day `/api/forecast`, all pages | Same before and after. `/dashboard` and `/api/health` differ only by the new tab and the new `simulator_60d` key |
| Embedded data in the dashboard (D, DASH, FC, FX, TEAM_*, VERIFIED_FINDINGS) | Byte-identical |
| `/api/health` and the launcher report | `Simulator 60d : LOADED (1000 draws, 2026-01-01 to 2026-03-01) - Decision Lab ready` |

## 5. Files

**Inner folder `TheProject\TheProject\`**
- **Backed up first:** `citizen_app.py`, `run_oasis.bat`, `run_oasis.sh`, `requirements.txt`, `README.md`, `install_requirements.py`, each as `*.bak_before_decision_lab`.
- **New:**
  - `simulator_service.py`;
  - `tests\test_simulator_api.py`;
  - `pytest.ini`, which limits a bare `pytest` to `tests\`, because the Datasets folder has its own unrelated tests;
  - `Ayat\PredectionModel\forecast_60d\`: a copy of all 20 handoff files. `forecast_60d_handoff\` is left as it is.
- **Changed:**
  - `citizen_app.py`: 4 routes in both servers, plus `simulator_60d` in `/api/health`;
  - `run_oasis.bat` / `.sh`: they install numpy, pandas, scipy and pytest once if any is missing, and print the simulator line in the report;
  - `requirements.txt`: new optional groups `simulator` and `tests`;
  - `install_requirements.py`: new `--groups` option;
  - `README.md`: endpoints with curl examples.

**Outer folder:** `oasis_city_system.html` (Decision Lab), with a backup `oasis_city_system.html.bak_before_decision_lab`.
