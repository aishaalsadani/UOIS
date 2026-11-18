"""simulate(zone, days, view, scenario, **params): the 60-day complaints simulator.

Usage (from the forecast_60d folder):
    from simulator_api import simulate
    r = simulate("Z01", days=30, view="weekly")                                  # normal
    r = simulate("ALL", days=60, view="monthly", scenario="ramadan_off")         # Ramadan effect
    r = simulate("Z01", days=60, scenario="fix", category="streetlights", start_date="2026-01-15", reduce_pct=30)
    r = simulate("Z04", days=60, scenario="population", new_population=9000)
    r["by_type"], r["by_period"], r["detail"], r["total"]  (+ r["by_zone"] for "ALL")

Reads only outputs/zone_forecast_60d.csv, outputs/zone_forecast_60d_ramadan_off.csv and model/model_card_60d.json
(no model, no LightGBM). Normal and scenario are drawn with the same random numbers, so their difference is the
effect of the scenario only.
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import poisson

HERE = Path(__file__).resolve().parent
FORECAST_FILE = HERE / "outputs" / "zone_forecast_60d.csv"
RAMADAN_OFF_FILE = HERE / "outputs" / "zone_forecast_60d_ramadan_off.csv"
CARD_FILE = HERE / "model" / "model_card_60d.json"
SCENARIOS = ("normal", "ramadan_off", "fix", "population")
VIEWS = ("daily", "weekly", "monthly")


@lru_cache(maxsize=1)
def _load():
    card = json.loads(CARD_FILE.read_text(encoding="utf-8"))
    fc = pd.read_csv(FORECAST_FILE)
    off = pd.read_csv(RAMADAN_OFF_FILE)
    fc = fc.merge(off[["zone", "day_number", "category_id", "mean_ramadan_off"]], on=["zone", "day_number", "category_id"])
    fc = fc.sort_values(["zone", "category_id", "day_number"], ignore_index=True)
    return card, fc


def _period(dates, view):
    d = pd.to_datetime(pd.Series(dates))
    if view == "daily":
        return d.dt.strftime("%Y-%m-%d").to_numpy()
    if view == "weekly":
        return np.array([f"week {i // 7 + 1}" for i in range(len(d))])
    return d.dt.strftime("%Y-%m").to_numpy()


def simulate(zone="ALL", days=60, view="daily", scenario="normal", n_sims=None, seed=None, **params):
    card, fc = _load()
    zones, cats = card["zone_order"], card["category_order"]
    horizon = card["horizon_days"]
    if zone != "ALL" and zone not in zones:
        raise ValueError(f"zone must be 'ALL' or one of {zones}, got {zone!r}")
    if isinstance(days, bool) or not isinstance(days, (int, np.integer)) or not 1 <= days <= horizon:
        raise ValueError(f"days must be a whole number from 1 to {horizon}, got {days!r}")
    if view not in VIEWS:
        raise ValueError(f"view must be one of {VIEWS}, got {view!r}")
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {SCENARIOS}, got {scenario!r}")
    sim = card["simulator"]
    n_sims = n_sims or sim["n_sims"]
    seed = sim["seed"] if seed is None else seed

    sel_z = zones if zone == "ALL" else [zone]
    sub = fc[fc["zone"].isin(sel_z) & (fc["day_number"] <= days)]
    nz = len(sel_z)
    mu_n = sub["mean"].to_numpy().reshape(nz, len(cats), days)
    dates = sub["date"].iloc[:days].to_numpy()
    mu_s = mu_n.copy()
    assumptions = [f"Simulator: {sim['distribution']}, sigma2 = {sim['sigma2']:.4f}, {n_sims} draws, seed {seed}."]

    if scenario == "ramadan_off":
        mu_s = sub["mean_ramadan_off"].to_numpy().reshape(nz, len(cats), days)
        r = card["assumptions"]["ramadan_2026"]
        assumptions.append(f"Normal includes Ramadan {r[0]} → {r[1]} (ASSUMED dates); scenario switches Ramadan off. "
                           "The effect is learned from Ramadan 2025 (before the app launch).")
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
        on = pd.to_datetime(dates) >= start
        mu_s[sel_z.index(fz), cats.index(cat), on] *= 1 - pct / 100
        assumptions.append(f"USER ASSUMPTION: {cat} complaints in {fz} drop {pct}% from {start.date()} on.")
    elif scenario == "population":
        pz = params.get("pop_zone", zone)
        new = params.get("new_population")
        if pz not in zones or pz not in sel_z:
            raise ValueError("population needs a specific zone (zone='Z04'… or pop_zone inside the selection)")
        if not isinstance(new, (int, float)) or isinstance(new, bool) or new <= 0:
            raise ValueError(f"new_population must be a positive number, got {new!r}")
        cur = card["population"][pz]
        mu_s[sel_z.index(pz)] *= new / cur
        assumptions.append(f"ASSUMPTION: {pz} population {cur:,} → {new:,.0f} (×{new / cur:.2f}) with the same "
                           "complaints per 1,000 residents for every type.")

    # Same random numbers for normal and scenario (common random numbers).
    rng = np.random.default_rng(seed)
    s2 = sim["sigma2"]
    level = rng.gamma(1 / s2, s2, size=(n_sims, nz, len(cats), 1)) if s2 > 0 else np.ones((n_sims, nz, len(cats), 1))
    u = rng.random((n_sims, nz, len(cats), days))
    draw = lambda mu: poisson.ppf(u, np.maximum(mu[None] * level, 1e-12)).astype(np.int32)
    S_n, S_s = draw(mu_n), draw(mu_s)

    per = _period(dates, view)
    plist = list(dict.fromkeys(per))

    def summarise(sum_axes, index):
        # sum_axes: axes of (nz, nt) to sum over; index: labels for the remaining axis (or None for total)
        out = []
        for p in plist + [None]:
            m = np.ones(days, bool) if p is None else (per == p)
            an, as_ = S_n[..., m].sum(-1), S_s[..., m].sum(-1)          # sims × nz × nt
            mn, ms = mu_n[..., m].sum(-1), mu_s[..., m].sum(-1)         # nz × nt
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
    detail = summarise((), None)
    detail.insert(1, "zone", np.tile(np.repeat(sel_z, len(cats)), len(plist) + 1))
    detail.insert(2, "category_id", np.tile(np.tile(cats, nz), len(plist) + 1))
    detail.insert(3, "pillar", detail["category_id"].map(pillar))
    total = by_period[by_period["period"] == "all selected days"].iloc[0].drop("period").to_dict()

    r2 = lambda d: d.round({c: 2 for c in ["normal_mean", "mean", "change", "change_pct"]})
    out = {"scenario": scenario, "zone": zone, "days": days, "view": view,
           "dates": [str(dates[0]), str(dates[-1])], "assumptions": assumptions,
           "by_type": r2(all_days.sort_values("mean", ascending=False, ignore_index=True)),
           "by_period": r2(by_period[by_period["period"] != "all selected days"].reset_index(drop=True)),
           "detail": r2(detail[detail["period"] != "all selected days"].reset_index(drop=True)),
           "total": {k: float(v) for k, v in total.items()}}
    if zone == "ALL":
        bz = summarise((1,), ("zone", sel_z))
        out["by_zone"] = r2(bz[bz["period"] == "all selected days"].drop(columns="period")
                            .sort_values("mean", ascending=False, ignore_index=True))
    return out


if __name__ == "__main__":
    r = simulate("ALL", days=60, view="monthly")
    print(r["dates"], r["total"])
    print(r["by_zone"])
