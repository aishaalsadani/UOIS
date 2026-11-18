"""Decision Lab service: Ayat's 60-day complaints simulator behind the Flask API.

The simulator itself is Ayat's `simulate()` in Ayat/PredectionModel/forecast_60d/simulator_api.py. It is loaded
as it is (not copied, not changed) and reads only outputs/*.csv and model/model_card_60d.json. No LightGBM.

Why there is a fast path
------------------------
One `simulate()` call takes about 2-4 s, because it draws 1,000 Poisson series for every zone x type x day twice
(normal and scenario). The Decision Lab updates live and the leaderboard needs 90 runs, so this module keeps the
draws of the normal case in memory, per (zone, days), and only re-draws the series a scenario actually changes.
It uses the same random numbers in the same order (same seed, same array shapes), the same scenario rules and the
same summary code as `simulate()`, so every number is identical. That is checked by
tests/test_simulator_api.py, and any request can be answered by the original function with engine="reference".
"""
import hashlib
import importlib.util
import json
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path

BASE = Path(__file__).resolve().parent
SIM_DIR = BASE / "Ayat" / "PredectionModel" / "forecast_60d"
CACHE_DIR = BASE / "cache"
LOG_FILE = BASE / "simulator_queries_log.json"
LEADERBOARD_DAYS = (30, 60)
LEADERBOARD_PCTS = (10, 20, 30, 50)
LEADERBOARD_START = "2026-01-01"

_lock = threading.RLock()
_state = {"module": None, "error": None, "loaded_at": None}
_arrays = OrderedDict()           # (zone, days, n_sims, seed) -> normal draws; small LRU
_results = OrderedDict()          # request key -> JSON result; LRU
_lb = {}                          # (days, pct) -> {"status", "done", "total", "result"}
_log_lock = threading.Lock()
_pool = {}


def _ppf(u, lam):
    """scipy.stats.poisson.ppf(u, lam), element by element. Large arrays are split into blocks of draws and run on
    all CPU cores (scipy's special functions release the GIL). Same function on the same numbers, so the result is
    identical to one call; only faster."""
    from scipy.stats import poisson
    import numpy as np
    n = u.shape[0]
    if u.size < 200_000 or (os.cpu_count() or 1) < 2 or n < 4:
        return poisson.ppf(u, lam)
    if "ex" not in _pool:
        from concurrent.futures import ThreadPoolExecutor
        _pool["ex"] = ThreadPoolExecutor(max_workers=max(1, min(16, (os.cpu_count() or 2) - 1)), thread_name_prefix="simulator-ppf")  # one core left for the rest
    cuts = np.linspace(0, n, min(n, 4 * (os.cpu_count() or 2)) + 1).astype(int)
    parts = list(_pool["ex"].map(lambda ab: poisson.ppf(u[ab[0]:ab[1]], lam[ab[0]:ab[1]]), zip(cuts[:-1], cuts[1:])))
    return np.concatenate(parts, axis=0)


# --------------------------------------------------------------------------- loading
def _load_module():
    with _lock:
        if _state["module"] is not None or _state["error"]:
            return _state["module"]
        try:
            path = SIM_DIR / "simulator_api.py"
            if not path.exists():
                raise FileNotFoundError(f"{path} not found (copy Ayat's forecast_60d folder there)")
            spec = importlib.util.spec_from_file_location("ayat_simulator_api_60d", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod._load()                                   # reads the CSVs and the model card once
            _state.update(module=mod, loaded_at=time.strftime("%Y-%m-%d %H:%M:%S"))
        except Exception as e:                            # reported by /api/health, never raised to the server
            _state["error"] = f"{type(e).__name__}: {e}"
        return _state["module"]


def available():
    return _load_module() is not None


def health():
    mod = _load_module()
    out = {"loaded": mod is not None, "error": _state["error"], "folder": str(SIM_DIR),
           "loaded_at": _state["loaded_at"]}
    if mod is not None:
        card, fc = mod._load()
        out.update(forecast_file=str(mod.FORECAST_FILE), rows=int(len(fc)), n_sims=card["simulator"]["n_sims"],
                   horizon_days=card["horizon_days"], dates=card["forecast_dates"],
                   leaderboard_cache={f"{d}d_{p}pct": _lb.get((d, p), {}).get("status", _disk_status(d, p))
                                      for d in LEADERBOARD_DAYS for p in LEADERBOARD_PCTS})
    return out


# --------------------------------------------------------------------------- JSON helpers
def _records(df):
    import math
    rows = df.to_dict(orient="records")
    return [{k: (None if isinstance(v, float) and math.isnan(v) else (v.item() if hasattr(v, "item") else v))
             for k, v in r.items()} for r in rows]


def _jsonify(res, focus=None, include_detail=False):
    import math
    out = {}
    for k, v in res.items():
        if hasattr(v, "to_dict"):
            if k == "detail" and not include_detail:
                continue
            out[k] = _records(v)
        elif k == "total":
            out[k] = {kk: (None if isinstance(vv, float) and math.isnan(vv) else vv) for kk, vv in v.items()}
        else:
            out[k] = v
    if focus is not None and "detail" in res:
        z, c = focus
        d = res["detail"]
        out["focus"] = {"zone": z, "category_id": c, "by_period": _records(d[(d["zone"] == z) & (d["category_id"] == c)])}
    return out


def period_dates(dates_all, view):
    """Start and end date of every period, so the page can draw them on a date axis."""
    import pandas as pd
    d = pd.to_datetime(pd.Series(dates_all))
    mod = _load_module()
    per = mod._period(dates_all, view)
    out = []
    for p in dict.fromkeys(per):
        m = per == p
        out.append({"period": str(p), "start": d[m].min().strftime("%Y-%m-%d"), "end": d[m].max().strftime("%Y-%m-%d")})
    return out


# --------------------------------------------------------------------------- fast exact engine
def _normal_arrays(zone, days, n_sims, seed):
    """Everything simulate() computes before the scenario: mean matrix, random numbers, normal draws."""
    import numpy as np
    from scipy.stats import poisson
    key = (zone, days, n_sims, seed)
    with _lock:
        if key in _arrays:
            _arrays.move_to_end(key)
            return _arrays[key]
    mod = _load_module()
    card, fc = mod._load()
    zones, cats = card["zone_order"], card["category_order"]
    sel_z = zones if zone == "ALL" else [zone]
    sub = fc[fc["zone"].isin(sel_z) & (fc["day_number"] <= days)]
    nz = len(sel_z)
    mu_n = sub["mean"].to_numpy().reshape(nz, len(cats), days)
    mu_off = sub["mean_ramadan_off"].to_numpy().reshape(nz, len(cats), days)
    dates = sub["date"].iloc[:days].to_numpy()
    sim = card["simulator"]
    rng = np.random.default_rng(seed)                     # same order and shapes as simulate()
    s2 = sim["sigma2"]
    level = rng.gamma(1 / s2, s2, size=(n_sims, nz, len(cats), 1)) if s2 > 0 else np.ones((n_sims, nz, len(cats), 1))
    u = rng.random((n_sims, nz, len(cats), days))
    S_n = _ppf(u, np.maximum(mu_n[None] * level, 1e-12)).astype(np.int32)
    item = {"sel_z": sel_z, "cats": cats, "mu_n": mu_n, "mu_off": mu_off, "dates": dates, "level": level, "u": u, "S_n": S_n}
    with _lock:
        _arrays[key] = item
        while len(_arrays) > 10:
            _arrays.popitem(last=False)
    return item


def _validate_and_scenario(mod, card, zone, days, view, scenario, params, A):
    """The checks and scenario rules of simulate(), in the same order, with the same messages."""
    import numpy as np
    import pandas as pd
    zones, cats = card["zone_order"], card["category_order"]
    sel_z = A["sel_z"]
    mu_s = A["mu_n"].copy()
    changed = None                                        # (zone index or None, category index or None, day mask)
    sim = card["simulator"]
    if scenario == "ramadan_off":
        mu_s = A["mu_off"].copy()
        changed = "all"
    elif scenario == "fix":
        fz = params.get("fix_zone", zone)
        cat, start, pct = params.get("category"), params.get("start_date"), params.get("reduce_pct")
        if fz not in zones:
            raise ValueError("fix needs a specific zone (zone='Z01'… or fix_zone='Z01'…)")
        if fz not in sel_z:
            raise ValueError(f"fix zone {fz} is not in the selected zone {zone}")
        if cat not in cats:
            raise ValueError(f"category must be one of {cats}, got {cat!r}")
        try:
            start = pd.Timestamp(start)
        except Exception:
            raise ValueError(f"start_date must be a date like '2026-01-15', got {params.get('start_date')!r}")
        if not isinstance(pct, (int, float)) or isinstance(pct, bool) or not 0 <= pct <= 100:
            raise ValueError(f"reduce_pct must be a number from 0 to 100, got {pct!r}")
        on = pd.to_datetime(A["dates"]) >= start
        mu_s[sel_z.index(fz), cats.index(cat), on] *= 1 - pct / 100
        changed = (sel_z.index(fz), cats.index(cat), on)
    elif scenario == "population":
        pz = params.get("pop_zone", zone)
        new = params.get("new_population")
        if pz not in zones or pz not in sel_z:
            raise ValueError("population needs a specific zone (zone='Z04'… or pop_zone inside the selection)")
        if not isinstance(new, (int, float)) or isinstance(new, bool) or new <= 0:
            raise ValueError(f"new_population must be a positive number, got {new!r}")
        cur = card["population"][pz]
        mu_s[sel_z.index(pz)] *= new / cur
        changed = (sel_z.index(pz), None, None)
    return mu_s, changed


def _assumptions(card, scenario, zone, n_sims, seed, params):
    """Same text as simulate() builds."""
    import pandas as pd
    sim = card["simulator"]
    a = [f"Simulator: {sim['distribution']}, sigma2 = {sim['sigma2']:.4f}, {n_sims} draws, seed {seed}."]
    if scenario == "ramadan_off":
        r = card["assumptions"]["ramadan_2026"]
        a.append(f"Normal includes Ramadan {r[0]} → {r[1]} (ASSUMED dates); scenario switches Ramadan off. "
                 "The effect is learned from Ramadan 2025 (before the app launch).")
    elif scenario == "fix":
        fz = params.get("fix_zone", zone)
        a.append(f"USER ASSUMPTION: {params.get('category')} complaints in {fz} drop {params.get('reduce_pct')}% "
                 f"from {pd.Timestamp(params.get('start_date')).date()} on.")
    elif scenario == "population":
        pz = params.get("pop_zone", zone)
        cur, new = card["population"][pz], params.get("new_population")
        a.append(f"ASSUMPTION: {pz} population {cur:,} → {new:,.0f} (×{new / cur:.2f}) with the same "
                 "complaints per 1,000 residents for every type.")
    return a


def fast_simulate(zone="ALL", days=60, view="daily", scenario="normal", n_sims=None, seed=None, need_detail=True, **params):
    """Same inputs, same outputs as simulate(); see the module docstring."""
    import numpy as np
    import pandas as pd
    from scipy.stats import poisson
    mod = _load_module()
    if mod is None:
        raise RuntimeError(_state["error"] or "simulator not loaded")
    card, fc = mod._load()
    zones, cats = card["zone_order"], card["category_order"]
    horizon = card["horizon_days"]
    if zone != "ALL" and zone not in zones:
        raise ValueError(f"zone must be 'ALL' or one of {zones}, got {zone!r}")
    if isinstance(days, bool) or not isinstance(days, (int, np.integer)) or not 1 <= days <= horizon:
        raise ValueError(f"days must be a whole number from 1 to {horizon}, got {days!r}")
    if view not in mod.VIEWS:
        raise ValueError(f"view must be one of {mod.VIEWS}, got {view!r}")
    if scenario not in mod.SCENARIOS:
        raise ValueError(f"scenario must be one of {mod.SCENARIOS}, got {scenario!r}")
    sim = card["simulator"]
    n_sims = n_sims or sim["n_sims"]
    seed = sim["seed"] if seed is None else seed

    A = _normal_arrays(zone, days, n_sims, seed)
    sel_z, mu_n, dates, level, u, S_n = A["sel_z"], A["mu_n"], A["dates"], A["level"], A["u"], A["S_n"]
    nz = len(sel_z)
    mu_s, changed = _validate_and_scenario(mod, card, zone, days, view, scenario, params, A)
    assumptions = _assumptions(card, scenario, zone, n_sims, seed, params)

    # re-draw only what the scenario changed; the same u and level give the same numbers as a full draw
    if changed is None:
        S_s = S_n
    elif changed == "all":                                # Ramadan off: no user parameter, so drawn once per (zone, days)
        if "S_off" not in A:
            A["S_off"] = _ppf(u, np.maximum(mu_s[None] * level, 1e-12)).astype(np.int32)
        S_s = A["S_off"]
    else:
        S_s = S_n.copy()
        zi, ci, on = changed
        if ci is None:
            S_s[:, zi] = _ppf(u[:, zi], np.maximum(mu_s[zi][None] * level[:, zi], 1e-12)).astype(np.int32)
        elif on.any():
            S_s[:, zi, ci, on] = poisson.ppf(u[:, zi, ci, on], np.maximum(mu_s[zi, ci, on][None] * level[:, zi, ci, :], 1e-12)).astype(np.int32)

    per = mod._period(dates, view)
    plist = list(dict.fromkeys(per))

    def summarise(sum_axes, index):                       # identical to simulate()'s inner function
        out = []
        for p in plist + [None]:
            m = np.ones(days, bool) if p is None else (per == p)
            an, as_ = S_n[..., m].sum(-1), S_s[..., m].sum(-1)
            mn, ms = mu_n[..., m].sum(-1), mu_s[..., m].sum(-1)
            if sum_axes:
                an, as_ = an.sum(axis=tuple(a + 1 for a in sum_axes)), as_.sum(axis=tuple(a + 1 for a in sum_axes))
                mn, ms = mn.sum(axis=sum_axes), ms.sum(axis=sum_axes)
            an, as_ = an.reshape(n_sims, -1), as_.reshape(n_sims, -1)
            mn, ms = np.ravel(mn), np.ravel(ms)
            qn, qs = np.percentile(an, [10, 90], axis=0), np.percentile(as_, [10, 90], axis=0)
            df = pd.DataFrame({"normal_mean": mn, "normal_p10": qn[0], "normal_p90": qn[1],
                               "mean": ms, "p10": qs[0], "p90": qs[1]})
            df["change"] = df["mean"] - df["normal_mean"]
            df["change_pct"] = 100 * df["change"] / df["normal_mean"].where(df["normal_mean"] > 0)
            if index is not None:
                df.insert(0, index[0], index[1])
            df.insert(0, "period", "all selected days" if p is None else p)
            out.append(df)
        return pd.concat(out, ignore_index=True)

    pillar = card["pillar"]
    by_type = summarise((0,), ("category_id", cats))
    by_type.insert(2, "pillar", by_type["category_id"].map(pillar))
    all_days = by_type[by_type["period"] == "all selected days"].drop(columns="period")
    by_period = summarise((0, 1), None).drop(columns=[])
    total = by_period[by_period["period"] == "all selected days"].iloc[0].drop("period").to_dict()
    r2 = lambda d: d.round({c: 2 for c in ["normal_mean", "mean", "change", "change_pct"]})
    out = {"scenario": scenario, "zone": zone, "days": days, "view": view,
           "dates": [str(dates[0]), str(dates[-1])], "assumptions": assumptions,
           "by_type": r2(all_days.sort_values("mean", ascending=False, ignore_index=True)),
           "by_period": r2(by_period[by_period["period"] != "all selected days"].reset_index(drop=True)),
           "total": {k: float(v) for k, v in total.items()}}
    if need_detail:
        detail = summarise((), None)
        detail.insert(1, "zone", np.tile(np.repeat(sel_z, len(cats)), len(plist) + 1))
        detail.insert(2, "category_id", np.tile(np.tile(cats, nz), len(plist) + 1))
        detail.insert(3, "pillar", detail["category_id"].map(pillar))
        out["detail"] = r2(detail[detail["period"] != "all selected days"].reset_index(drop=True))
        out = {k: out[k] for k in ["scenario", "zone", "days", "view", "dates", "assumptions", "by_type", "by_period", "detail", "total"]}
    if zone == "ALL":
        bz = summarise((1,), ("zone", sel_z))
        out["by_zone"] = r2(bz[bz["period"] == "all selected days"].drop(columns="period")
                            .sort_values("mean", ascending=False, ignore_index=True))
    return out


# --------------------------------------------------------------------------- request handling
ALLOWED = {"zone", "days", "view", "scenario", "category", "start_date", "reduce_pct", "new_population",
           "fix_zone", "pop_zone", "n_sims", "seed"}


def _clean_request(data):
    if not isinstance(data, dict):
        raise ValueError("send a JSON object")
    unknown = set(data) - ALLOWED - {"include_detail", "engine", "focus"}
    if unknown:
        raise ValueError(f"unknown field(s): {sorted(unknown)}")
    req = {k: v for k, v in data.items() if k in ALLOWED and v is not None}
    if "days" in req and isinstance(req["days"], float) and req["days"].is_integer():
        req["days"] = int(req["days"])
    req.setdefault("zone", "ALL"); req.setdefault("days", 60); req.setdefault("view", "weekly"); req.setdefault("scenario", "normal")
    # only pass the parameters the chosen scenario uses (simulate() ignores the rest anyway)
    keep = {"fix": {"category", "start_date", "reduce_pct", "fix_zone"}, "population": {"new_population", "pop_zone"}}.get(req["scenario"], set())
    return {k: v for k, v in req.items() if k in {"zone", "days", "view", "scenario", "n_sims", "seed"} | keep}


def simulate_request(data):
    """POST /api/simulate. Returns (http_status, json_dict)."""
    t0 = time.time()
    try:
        if not available():
            return 503, {"ok": False, "error": "simulator not loaded: " + str(_state["error"])}
        req = _clean_request(data)
        engine = (data or {}).get("engine", "fast")
        if engine not in ("fast", "reference"):
            raise ValueError("engine must be 'fast' or 'reference'")
        include_detail = bool((data or {}).get("include_detail"))
        focus = None
        if req["scenario"] == "fix" and req.get("category"):
            focus = (req.get("fix_zone", req["zone"]), req["category"])
        key = json.dumps([req, engine, include_detail], sort_keys=True)
        with _lock:
            cached = _results.get(key)
        hit = cached is not None
        if cached is None:
            if engine == "reference":
                res = _load_module().simulate(**req)
            else:
                res = fast_simulate(**req, need_detail=bool(include_detail or focus))
            body = _jsonify(res, focus=focus if "detail" in res else None, include_detail=include_detail)
            mod = _load_module()
            card, fc = mod._load()
            one = fc[(fc["zone"] == card["zone_order"][0]) & (fc["category_id"] == card["category_order"][0])]
            dates_all = one.sort_values("day_number")["date"].iloc[:req["days"]].to_numpy()
            body["period_dates"] = period_dates(dates_all, req["view"])
            body["engine"] = "simulate() reference" if engine == "reference" else "fast exact path (same draws as simulate())"
            body["ok"] = True
            with _lock:
                _results[key] = body
                while len(_results) > 300:
                    _results.popitem(last=False)
            cached = body
        out = dict(cached)
        out["latency_ms"] = round((time.time() - t0) * 1000, 1)
        out["cached"] = hit
        _log({"route": "/api/simulate", "request": req, "engine": engine, "ok": True, "latency_ms": out["latency_ms"]})
        return 200, out
    except ValueError as e:
        _log({"route": "/api/simulate", "request": data, "ok": False, "error": str(e)})
        return 400, {"ok": False, "error": str(e)}
    except Exception as e:
        _log({"route": "/api/simulate", "request": data, "ok": False, "error": f"{type(e).__name__}: {e}"})
        return 500, {"ok": False, "error": f"{type(e).__name__}: {e}"}


def frames_request(data):
    """POST /api/simulate/frames: the Play animation. reduce_pct from 0 to the chosen value in `steps` steps,
    each frame a real fix run (only the fields the page animates)."""
    t0 = time.time()
    try:
        if not available():
            return 503, {"ok": False, "error": "simulator not loaded: " + str(_state["error"])}
        data = dict(data or {})
        steps = data.pop("steps", 10)
        if isinstance(steps, bool) or not isinstance(steps, int) or not 2 <= steps <= 20:
            raise ValueError("steps must be a whole number from 2 to 20")
        req = _clean_request(data)
        if req["scenario"] != "fix":
            raise ValueError("frames are only for scenario 'fix'")
        target = req.get("reduce_pct")
        if not isinstance(target, (int, float)) or isinstance(target, bool) or not 0 <= target <= 100:
            raise ValueError(f"reduce_pct must be a number from 0 to 100, got {target!r}")
        fz, cat = req.get("fix_zone", req["zone"]), req.get("category")
        frames = []
        for k in range(steps + 1):
            pct = round(target * k / steps, 2)
            r = fast_simulate(**{**req, "reduce_pct": pct}, need_detail=True)
            d = r["detail"]
            frames.append({"reduce_pct": pct, "total": r["total"],
                           "focus_total": _records(r["by_type"][r["by_type"]["category_id"] == cat])[0] if cat else None,
                           "focus": _records(d[(d["zone"] == fz) & (d["category_id"] == cat)]) if cat else None,
                           "by_period": _records(r["by_period"])})
        out = {"ok": True, "frames": frames, "latency_ms": round((time.time() - t0) * 1000, 1)}
        _log({"route": "/api/simulate/frames", "request": req, "steps": steps, "ok": True, "latency_ms": out["latency_ms"]})
        return 200, out
    except ValueError as e:
        return 400, {"ok": False, "error": str(e)}


def meta():
    """GET /api/simulate/meta: everything the page shows that is not a simulation result."""
    import pandas as pd
    if not available():
        return 503, {"ok": False, "error": "simulator not loaded: " + str(_state["error"])}
    mod = _load_module()
    card, fc = mod._load()
    acc = pd.read_csv(SIM_DIR / "outputs" / "accuracy_60d.csv")
    a = acc[(acc["exams"] == "B only") & (acc["method"] == card["model"]) & (acc["zone"] == "ALL") & acc["view"].isin(["daily", "weekly", "monthly"])]
    accuracy = {v: {lvl: float(a[(a["view"] == v) & (a["level"] == lvl)]["accuracy"].iloc[0]) for lvl in ("zone x type", "zone total", "city x type")}
                for v in ("daily", "weekly", "monthly")}
    cov = pd.read_csv(SIM_DIR / "outputs" / "simulator_coverage_60d.csv")
    c = cov[cov["distribution"].str.lower().str.startswith("negative")].iloc[-1]
    lo, hi = card["forecast_dates"]
    hol = [h for h in card["holidays"] if lo <= h <= hi]
    return 200, {"ok": True, "zones": card["zone_order"], "categories": [{"category_id": k, "pillar": card["pillar"][k]} for k in card["category_order"]],
                 "population": card["population"], "horizon_days": card["horizon_days"], "first_date": lo, "last_date": hi,
                 "ramadan": {"start": card["assumptions"]["ramadan_2026"][0], "end": card["assumptions"]["ramadan_2026"][1], "assumed": True},
                 "holidays": hol, "accuracy_pct": accuracy, "accuracy_source": "outputs/accuracy_60d.csv · exam B (1 Nov–30 Dec 2025) · " + card["model"],
                 "coverage_pct": {"daily": float(c["daily P10–P90 coverage %"]), "weekly": float(c["weekly P10–P90 coverage %"]),
                                  "monthly": float(c["monthly P10–P90 coverage %"]), "exam": str(c["exam"])},
                 "n_sims": card["simulator"]["n_sims"], "distribution": card["simulator"]["distribution"],
                 "leaderboard": {"days": list(LEADERBOARD_DAYS), "reduce_pct": list(LEADERBOARD_PCTS), "start_date": LEADERBOARD_START}}


# --------------------------------------------------------------------------- leaderboard
_fp = {}


def _fingerprint():
    """Hash of the forecast files, the model card and the code: a changed forecast never uses an old cache."""
    if "v" in _fp:
        return _fp["v"]
    mod = _load_module()
    h = hashlib.sha256()
    for p in (mod.FORECAST_FILE, mod.RAMADAN_OFF_FILE, mod.CARD_FILE, SIM_DIR / "simulator_api.py", Path(__file__)):
        h.update(Path(p).read_bytes())
    _fp["v"] = h.hexdigest()[:16]
    return _fp["v"]


def _disk_path(days, pct):
    return CACHE_DIR / f"leaderboard_{days}_{pct}.json"


def _disk_status(days, pct):
    try:
        return "ready (disk)" if json.loads(_disk_path(days, pct).read_text(encoding="utf-8")).get("fingerprint") == _fingerprint() else "stale"
    except Exception:
        return "not computed"


def _compute_leaderboard(days, pct):
    mod = _load_module()
    card, fc = mod._load()
    zones, cats = card["zone_order"], card["category_order"]
    state = _lb[(days, pct)]
    rows, t0 = [], time.time()
    for z in zones:
        for c in cats:
            r = fast_simulate(zone=z, days=days, view="weekly", scenario="fix", category=c,
                              start_date=LEADERBOARD_START, reduce_pct=pct, need_detail=False)
            t = r["by_type"][r["by_type"]["category_id"] == c].iloc[0]
            prevented = float(t["normal_mean"] - t["mean"])
            rows.append({"zone": z, "category_id": c, "pillar": card["pillar"][c],
                         "prevented": round(prevented, 2), "prevented_pct": round(100 * prevented / t["normal_mean"], 2) if t["normal_mean"] > 0 else None,
                         "normal_total": float(t["normal_mean"]), "normal_p10": float(t["normal_p10"]), "normal_p90": float(t["normal_p90"]),
                         "scenario_total": float(t["mean"]), "p10": float(t["p10"]), "p90": float(t["p90"])})
            state["done"] = len(rows)
    rows.sort(key=lambda r: (-r["prevented"], r["zone"], r["category_id"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    result = {"ok": True, "status": "ready", "days": days, "reduce_pct": pct, "start_date": LEADERBOARD_START, "runs": len(rows),
              "top": rows[:10], "best_per_zone": {z: next(r for r in rows if r["zone"] == z) for z in zones},
              "computed_at": time.strftime("%Y-%m-%d %H:%M:%S"), "compute_seconds": round(time.time() - t0, 1),
              "fingerprint": _fingerprint(),
              "method": "90 runs of scenario 'fix' (one per zone × type), ranked by normal_mean − mean of that type in that zone over all selected days"}
    CACHE_DIR.mkdir(exist_ok=True)
    tmp = _disk_path(days, pct).with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, _disk_path(days, pct))
    return result


def _run_leaderboard(days, pct):
    try:
        res = _compute_leaderboard(days, pct)
        _lb[(days, pct)].update(status="ready", result=res)
    except Exception as e:
        _lb[(days, pct)].update(status="error", error=f"{type(e).__name__}: {e}")


def leaderboard_request(args, wait=False):
    """GET /api/simulate/leaderboard?days=60&reduce_pct=30 -> (status, json). 202 while it is being computed."""
    t0 = time.time()
    try:
        if not available():
            return 503, {"ok": False, "error": "simulator not loaded: " + str(_state["error"])}
        try:
            days, pct = int(args.get("days", 60)), int(args.get("reduce_pct", 30))
        except Exception:
            raise ValueError("days and reduce_pct must be whole numbers")
        if days not in LEADERBOARD_DAYS:
            raise ValueError(f"days must be one of {list(LEADERBOARD_DAYS)}")
        if pct not in LEADERBOARD_PCTS:
            raise ValueError(f"reduce_pct must be one of {list(LEADERBOARD_PCTS)}")
        key = (days, pct)
        with _lock:
            st = _lb.get(key)
            if st is None or st["status"] == "error":
                disk = None
                try:
                    disk = json.loads(_disk_path(days, pct).read_text(encoding="utf-8"))
                    if disk.get("fingerprint") != _fingerprint():
                        disk = None
                except Exception:
                    pass
                if disk:
                    st = _lb[key] = {"status": "ready", "done": 90, "total": 90, "result": disk}
                else:
                    st = _lb[key] = {"status": "computing", "done": 0, "total": 90, "result": None}
                    threading.Thread(target=_run_leaderboard, args=key, daemon=True).start()
        if wait:
            while st["status"] == "computing":
                time.sleep(0.2)
        if st["status"] == "ready":
            out = dict(st["result"]); out["cached"] = True; out["latency_ms"] = round((time.time() - t0) * 1000, 1)
            return 200, out
        if st["status"] == "error":
            return 500, {"ok": False, "status": "error", "error": st.get("error")}
        return 202, {"ok": True, "status": "computing", "done": st["done"], "total": st["total"], "days": days, "reduce_pct": pct}
    except ValueError as e:
        return 400, {"ok": False, "error": str(e)}


def warm_up():
    """Started in a background thread when the server starts: load the CSVs, fill the default leaderboard, then
    prepare the whole-city draws so the first 'Whole city' view in the Time Machine is quick."""
    def run():
        if available():
            leaderboard_request({"days": 60, "reduce_pct": 30}, wait=True)
            try:
                card = _load_module()._load()[0]
                for z in ("Z01", "ALL"):                  # Ramadan view of the default zone and of the whole city
                    fast_simulate(zone=z, days=60, view="weekly", scenario="ramadan_off", need_detail=False)
            except Exception:
                pass
    threading.Thread(target=run, daemon=True, name="simulator-warm-up").start()


def _log(entry):
    entry = dict(entry, time=time.strftime("%Y-%m-%d %H:%M:%S"))
    with _log_lock:
        try:
            items = json.loads(LOG_FILE.read_text(encoding="utf-8")) if LOG_FILE.exists() else []
        except Exception:
            items = []
        items = (items + [entry])[-500:]
        try:
            LOG_FILE.write_text(json.dumps(items, ensure_ascii=False, default=str), encoding="utf-8")
        except Exception:
            pass


# --------------------------------------------------------------------------- web routes (used by citizen_app.py)
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Allow-Private-Network": "true"}
ROUTES = ("/api/simulate", "/api/simulate/meta", "/api/simulate/leaderboard", "/api/simulate/frames")


def dispatch(method, path, query=None, body=None):
    """One place for both servers. Returns (status, dict) or None if the path is not a simulator route.
    `body` is the raw request text for POST."""
    if path not in ROUTES:
        return None
    if method == "OPTIONS":
        return 204, None
    if path == "/api/simulate/meta":
        return meta() if method == "GET" else (405, {"ok": False, "error": "use GET"})
    if path == "/api/simulate/leaderboard":
        return leaderboard_request(query or {}) if method == "GET" else (405, {"ok": False, "error": "use GET"})
    if method != "POST":
        return 405, {"ok": False, "error": "use POST with a JSON body"}
    try:
        data = json.loads(body or "")
    except Exception:
        return 400, {"ok": False, "error": "the request body must be JSON, for example {\"zone\": \"Z01\", \"days\": 60}"}
    return simulate_request(data) if path == "/api/simulate" else frames_request(data)


def register_flask_routes(app):
    from flask import Response, request

    def view():
        q = {k: v for k, v in request.args.items()}
        status, body = dispatch(request.method, request.path, q, request.get_data(as_text=True))
        resp = Response("" if body is None else json.dumps(body, ensure_ascii=False, allow_nan=False, default=str),
                        status=status, mimetype="application/json")
        for k, v in CORS.items():
            resp.headers[k] = v
        return resp

    for r in ROUTES:
        app.add_url_rule(r, endpoint="simulator_" + r.strip("/").replace("/", "_"), view_func=view,
                         methods=["GET", "POST", "OPTIONS"])


def handle_builtin(handler, method, path, query, body):
    """For citizen_app's fallback http.server. Returns True if it answered."""
    res = dispatch(method, path, {k: v[0] for k, v in (query or {}).items()}, body)
    if res is None:
        return False
    status, data = res
    out = b"" if data is None else json.dumps(data, ensure_ascii=False, allow_nan=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(out)))
    for k, v in CORS.items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(out)
    return True
