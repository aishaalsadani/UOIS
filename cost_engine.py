"""Cost of Delay engine (rules and statistics only, no trained model).

Turns what the project already measures into money and risk:
    - As-Is 2025: what open faults and losses cost, per pillar
    - To-Be: repair-time scenarios X -> Y and the saving Z (conservative / target / stretch)
    - Water loss (non-revenue water): 24.9% -> 20% -> 15%
    - Live: what is still open at the end of the data, and the loss that keeps running every day
    - Risk index 0-100 per pillar (citizen_impact_weights.csv)

Money is only computed from prices in CostEngine/cost_assumptions.csv that are filled in.
Everything else is reported in hours, units and risk.

Usage:
    python cost_engine.py            -> recompute and write CostEngine/outputs/
Standard library only. Every path is built from this file's folder, like citizen_app.py.
"""
import csv
import json
import os
import statistics as st
import time
from collections import defaultdict
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.join(BASE_DIR, "CostEngine")
ASSUMPTIONS = os.path.join(ENGINE_DIR, "cost_assumptions.csv")
OUT_DIR = os.path.join(ENGINE_DIR, "outputs")
SUMMARY_JSON = os.path.join(OUT_DIR, "cost_summary.json")
SRC = os.path.join(BASE_DIR, "Datasets", "EarlyWarnings data", "01_CLEAN_SOURCE_CSV")
SUP = os.path.join(BASE_DIR, "Datasets", "EarlyWarnings data", "02_SUPPORTING_CSV")
WARN = os.path.join(BASE_DIR, "Datasets", "main data", "Oasis_Service_Intelligence_FINAL", "Oasis_Service_Intelligence_FINAL",
                    "evaluation", "warning_evidence", "warning_evidence_table.csv")
DATASET_LABEL = "SYNTHETIC: Oasis District 2025 training kit, not real ACUD data"
ENGINE_VERSION = "1.0"

PILLARS = ["energy", "buildings", "water", "waste", "citizen_services", "environment", "mobility", "public_safety"]
# Asset-id prefix is cleaner than the free-text category (spelling variants such as "hvac", "C.C.T.V").
PREFIX_CATEGORY = {"VLV": "Water network", "PMP": "Water network", "SL": "Streetlight", "CAM": "CCTV", "BIN": "Waste bin",
                   "TSG": "Traffic signal", "HVAC": "HVAC", "DET": "Sensor"}
CATEGORY_PILLAR = {"Water network": "water", "Streetlight": "energy", "CCTV": "public_safety", "Waste bin": "waste",
                   "Traffic signal": "mobility", "HVAC": "buildings", "Sensor": "citizen_services"}
CATEGORY_FAMILY = {"Water network": "water_pressure", "Streetlight": "electricity", "CCTV": "cctv", "Waste bin": "waste_bins",
                   "Traffic signal": "traffic", "HVAC": "bms"}
PRIORITY_WEIGHT = {"P1": 4, "P2": 3, "P3": 2, "P4": 1}
MIN_GROUP = 10       # below this, the P25 benchmark falls back from category x priority to category
BIN_FULL_PCT = 90    # a bin at or above this fill level counts as overflowing
NIGHT_HOURS = 12     # a dark street lamp is a risk for one night per fault day


# ----------------------------------------------------------------------------- helpers
def _rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        yield from csv.DictReader(f)


def _ts(s):
    return datetime.fromisoformat(s[:19])


def _p25(values):
    v = sorted(values)
    return st.quantiles(v, n=4)[0] if len(v) >= 2 else v[0]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_assumptions(path=ASSUMPTIONS):
    out = {}
    for r in _rows(path):
        out[r["key"]] = {"value": _num(r["value"]), "unit": r["unit"], "status": r["status"], "source": r["source"],
                         "link": r.get("link", ""), "note": r.get("note", "")}
    return out


def _price(a, key):
    return a[key]["value"] if key in a else None


# ----------------------------------------------------------------------------- inputs derived from project data
def derive_from_warnings():
    """Typical leak size and HVAC excess (median peak - baseline) and the sensor's lead over the first complaint."""
    lead, excess, elec_kwh, elec_n = defaultdict(list), defaultdict(list), 0.0, 0
    for r in _rows(WARN):
        if r["lead_minutes_to_first_complaint"]:
            lead[r["family"]].append(float(r["lead_minutes_to_first_complaint"]))
        d = (_num(r["peak_value"]) or 0) - (_num(r["baseline_median_at_peak"]) or 0)
        if d > 0:
            excess[(r["family"], r["peak_variable"])].append(d)
            if r["family"] == "electricity" and r["peak_variable"] == "kwh":
                elec_kwh += d
                elec_n += 1
    leak = excess.get(("water_pressure", "flow_lps"))
    hvac = excess.get(("bms", "hvac_kw"))
    return {"lead_min": {k: st.median(v) for k, v in lead.items()},
            "leak_excess_lps": st.median(leak) if leak else None,
            "hvac_excess_kw": st.median(hvac) if hvac else None,
            "electricity_anomaly_excess_kwh": elec_kwh, "electricity_anomaly_count": elec_n}


def rate_per_hour(category, a, d):
    """EGP per hour a fault stays open, or None when a needed price is missing."""
    if category == "Water network" and d["leak_excess_lps"] and _price(a, "water_price_egp_m3") is not None:
        return d["leak_excess_lps"] * 3.6 * _price(a, "water_price_egp_m3")  # L/s -> m3/h
    if category == "HVAC" and d["hvac_excess_kw"] and _price(a, "electricity_egp_kwh") is not None:
        return d["hvac_excess_kw"] * _price(a, "electricity_egp_kwh")
    if category == "Waste bin":
        return _price(a, "waste_overflow_egp_hour")
    return None  # Streetlight (dark lamp), CCTV, Traffic signal, Sensor: risk and hours until a price exists


# ----------------------------------------------------------------------------- work orders: X -> Y -> Z
def work_orders(a, d):
    closed, open_ = [], []
    for r in _rows(os.path.join(SRC, "work_orders.csv")):
        cat = PREFIX_CATEGORY.get(r["asset_id"].split("-")[0], r["category"].strip())
        rec = {"work_order_id": r["work_order_id"], "asset_id": r["asset_id"], "category": cat,
               "pillar": CATEGORY_PILLAR.get(cat, ""), "priority": r["priority"], "sla_hours": float(r["sla_hours"]),
               "opened_at": r["opened_at"]}
        if r["status"].strip() == "closed" and r["closed_at"]:
            x = (_ts(r["closed_at"]) - _ts(r["opened_at"])).total_seconds() / 3600
            if x >= 0:
                rec["x_hours"] = x
                closed.append(rec)
        else:
            rec["status"] = r["status"].strip()
            open_.append(rec)

    by_cp, by_c = defaultdict(list), defaultdict(list)
    for r in closed:
        by_cp[(r["category"], r["priority"])].append(r["x_hours"])
        by_c[r["category"]].append(r["x_hours"])
    bench = {k: _p25(v) for k, v in by_cp.items() if len(v) >= MIN_GROUP}
    bench_c = {k: _p25(v) for k, v in by_c.items()}

    for r in closed:
        x, cat = r["x_hours"], r["category"]
        lead_h = d["lead_min"].get(CATEGORY_FAMILY.get(cat), 0.0) / 60
        r["y_conservative"] = min(x, r["sla_hours"])
        r["y_target"] = min(x, bench.get((cat, r["priority"]), bench_c[cat]))
        r["y_stretch"] = max(0.0, r["y_target"] - lead_h)
        rate = rate_per_hour(cat, a, d)
        for s in ("conservative", "target", "stretch"):
            saved = x - r["y_" + s]
            r["saved_h_" + s] = saved
            r["risk_h_" + s] = saved * PRIORITY_WEIGHT.get(r["priority"], 1)
            r["egp_" + s] = saved * rate if rate is not None else None

    to_be = []
    for cat in sorted(by_c, key=lambda c: -len(by_c[c])):
        g = [r for r in closed if r["category"] == cat]
        rate = rate_per_hour(cat, a, d)
        row = {"category": cat, "pillar": CATEGORY_PILLAR.get(cat, ""), "n_work_orders": len(g),
               "x_mean_h": st.mean(r["x_hours"] for r in g), "x_median_h": st.median(r["x_hours"] for r in g),
               "p25_h": bench_c[cat], "sla_breach_pct": 100 * sum(r["x_hours"] > r["sla_hours"] for r in g) / len(g),
               "open_hours_total": sum(r["x_hours"] for r in g),
               "early_warning_lead_min": d["lead_min"].get(CATEGORY_FAMILY.get(cat)), "egp_per_open_hour": rate,
               "as_is_egp": sum(r["x_hours"] for r in g) * rate if rate is not None else None}
        for s in ("conservative", "target", "stretch"):
            row["y_mean_h_" + s] = st.mean(r["y_" + s] for r in g)
            row["saved_h_" + s] = sum(r["saved_h_" + s] for r in g)
            row["risk_h_" + s] = sum(r["risk_h_" + s] for r in g)
            row["egp_" + s] = sum(r["egp_" + s] for r in g) if rate is not None else None
        # ROI without repair prices: the most a faster repair may cost per work order and still pay for itself
        row["break_even_egp_per_wo_target"] = row["egp_target"] / len(g) if row["egp_target"] is not None else None
        to_be.append(row)
    return closed, open_, to_be


# ----------------------------------------------------------------------------- As-Is by pillar (2025)
def water_loss(a):
    billed = sum(float(r["m3"]) for r in _rows(os.path.join(SRC, "water_meters.csv")))
    price = _price(a, "water_price_egp_m3")
    out = {"billed_m3_year": billed, "price_egp_m3": price, "levels": []}
    for key, label in (("nrw_baseline", "As-Is"), ("nrw_target", "Target"), ("nrw_stretch", "Stretch")):
        nrw = _price(a, key)
        lost = billed * nrw / (1 - nrw)  # billed volume is fixed; losses sit on top of it
        out["levels"].append({"level": label, "nrw": nrw, "lost_m3_year": lost, "lost_m3_day": lost / 365,
                              "egp_year": lost * price if price is not None else None})
    base = out["levels"][0]
    for lv in out["levels"]:
        lv["saved_m3_year"] = base["lost_m3_year"] - lv["lost_m3_year"]
        lv["saved_egp_year"] = lv["saved_m3_year"] * price if price is not None else None
    out["note"] = ("The district has no metered inflow at its border, so its loss share cannot be measured from the "
                   "data. The national rate (24.9%) is applied to the billed volume of the 327 metered buildings.")
    return out


def hvac_idle(a):
    """Energy an HVAC unit draws in an empty building above that building's own normal idle level."""
    idle = defaultdict(list)
    path = os.path.join(SRC, "bms_readings.csv")
    for r in _rows(path):
        if r["occupancy_count"] == "0" and r["hvac_kw"]:
            idle[r["building_id"]].append(float(r["hvac_kw"]))
    med = {b: st.median(v) for b, v in idle.items()}
    excess = 0.0
    for b, v in idle.items():
        excess += sum(x - med[b] for x in v if x > med[b])  # hourly readings -> kWh
    price = _price(a, "electricity_egp_kwh")
    return {"buildings": len(med), "excess_kwh": excess, "egp": excess * price if price is not None else None}


def bins_full():
    hours, bins = 0, set()
    for r in _rows(os.path.join(SRC, "bin_fill.csv")):
        v = _num(r["fill_pct"])
        if v is not None and v >= BIN_FULL_PCT:
            hours += 1  # hourly readings
            bins.add(r["bin_id"])
    return {"bin_hours": hours, "bins": len(bins)}


def camera_down():
    hours, cams = 0.0, set()
    for r in _rows(os.path.join(SRC, "camera_status.csv")):
        v = _num(r["uptime_pct"])
        if v is not None and v < 100:
            hours += (100 - v) / 100 * 24
            cams.add(r["camera_id"])
    return {"camera_hours_down": hours, "cameras": len(cams)}


def lamps_dark():
    days = defaultdict(int)
    for r in _rows(os.path.join(SRC, "streetlights.csv")):
        if r["status"] in ("fault", "off"):
            days[r["status"]] += 1
    return {"fault_days": days["fault"], "off_days": days["off"], "dark_lamp_hours": (days["fault"] + days["off"]) * NIGHT_HOURS}


def complaints(a):
    sla = _price(a, "complaint_sla_hours") or 48
    cat_pillar = {r["category_name_ar"].strip(): r["pillar"] for r in _rows(os.path.join(SUP, "complaint_categories.csv"))}
    per_pillar = defaultdict(int)
    zones = defaultdict(set)
    late, late_hours, closed = 0, 0.0, 0
    for r in _rows(os.path.join(SRC, "service_requests.csv")):
        p = cat_pillar.get(r["category"].strip())
        if p:
            per_pillar[p] += 1
            zones[p].add(r["zone_id"])
        if r["status"] == "closed" and r["closed_at"]:
            h = (_ts(r["closed_at"]) - _ts(r["created_at"])).total_seconds() / 3600
            if h >= 0:
                closed += 1
                if h > sla:
                    late += 1
                    late_hours += h - sla
    price = _price(a, "complaint_handling_egp")
    return {"sla_hours": sla, "closed": closed, "late": late, "late_share": late / closed if closed else 0,
            "hours_beyond_sla": late_hours, "per_pillar": dict(per_pillar),
            "zones_per_pillar": {k: len(v) for k, v in zones.items()},
            "egp": None if price is None else late * price}


def air_exposure(a):
    thr = _price(a, "pm25_daily_threshold") or 37.5
    day = defaultdict(list)
    for r in _rows(os.path.join(SRC, "air_quality.csv")):
        v = _num(r["pm25"])
        if v is not None:
            day[(r["station_id"], r["timestamp"][:10])].append(v)
    over = sum(1 for v in day.values() if st.mean(v) > thr)
    return {"threshold": thr, "station_days": len(day), "station_days_over": over}


def as_is(a, d, to_be, nrw):
    cat = {r["category"]: r for r in to_be}
    hv, bins, cams, lamps, comp, air = hvac_idle(a), bins_full(), camera_down(), lamps_dark(), complaints(a), air_exposure(a)
    price_kwh = _price(a, "electricity_egp_kwh")
    elec_egp = d["electricity_anomaly_excess_kwh"] * price_kwh if price_kwh is not None else None

    def wo(c):
        r = cat.get(c, {})
        return r.get("open_hours_total", 0.0), r.get("as_is_egp")

    lines = []

    def add(pillar, metric, qty, unit, egp, basis):
        lines.append({"pillar": pillar, "metric": metric, "quantity": qty, "unit": unit, "egp": egp, "basis": basis})

    h, e = wo("Water network")
    add("water", "Open water-network faults", h, "fault-hours", e, "fault-hours x typical leak (L/s) x 3.6 x water price")
    add("water", "Water loss at the national rate", nrw["levels"][0]["lost_m3_year"], "m3/year", nrw["levels"][0]["egp_year"],
        "billed m3 x 24.9% / (1 - 24.9%) x water price")
    h, e = wo("HVAC")
    add("buildings", "Open HVAC faults", h, "fault-hours", e, "fault-hours x typical HVAC excess (kW) x electricity price")
    add("buildings", "HVAC running in empty buildings above normal idle", hv["excess_kwh"], "kWh", hv["egp"],
        "sum of (hvac_kw - building's idle median) while occupancy = 0 x electricity price")
    add("energy", "Electricity spikes caught by the early warning", d["electricity_anomaly_excess_kwh"], "kWh", elec_egp,
        "sum of (peak - baseline) kWh of electricity warnings x electricity price (lower bound: one reading each)")
    h, _ = wo("Streetlight")
    add("energy", "Open streetlight faults", h, "fault-hours", None, "needs lamp power and repair cost")
    add("public_safety", "Dark lamp-nights (fault or off)", lamps["dark_lamp_hours"], "lamp-hours", None, "risk only")
    add("public_safety", "Camera downtime", cams["camera_hours_down"], "camera-hours", None, "risk only")
    h, _ = wo("CCTV")
    add("public_safety", "Open CCTV faults", h, "fault-hours", None, "risk only")
    add("waste", "Bins at or above 90% full", bins["bin_hours"], "bin-hours", None, "needs cleanup cost per bin-hour")
    h, _ = wo("Waste bin")
    add("waste", "Open waste-bin faults", h, "fault-hours", None, "needs cleanup cost")
    h, _ = wo("Traffic signal")
    add("mobility", "Open traffic-signal faults", h, "fault-hours", None, "needs value of time")
    add("citizen_services", "Complaints closed after the 48 h SLA", comp["late"], "complaints", comp["egp"],
        "needs complaint handling cost")
    add("citizen_services", "Hours beyond the complaint SLA", comp["hours_beyond_sla"], "hours", None, "risk only")
    add("environment", "Station-days above the WHO PM2.5 interim target", air["station_days_over"], "station-days", None,
        "exposure indicator only")
    return lines, {"hvac": hv, "bins": bins, "cameras": cams, "lamps": lamps, "complaints": comp, "air": air}


# ----------------------------------------------------------------------------- risk index 0-100 per pillar
def risk_index(closed, comp, extra):
    w = {r["component"]: float(r["weight_pct"]) for r in _rows(os.path.join(SUP, "citizen_impact_weights.csv"))}
    pw = {r["pillar"]: float(r["weight_pct"]) for r in _rows(os.path.join(SUP, "pillar_weights.csv"))}
    max_pw, max_c = max(pw.values()), max(comp["per_pillar"].values() or [1])
    by_p = defaultdict(list)
    for r in closed:
        by_p[r["pillar"]].append(r)
    out = []
    for p in PILLARS:
        parts = {}
        g = by_p.get(p)
        if g:
            parts["severity"] = st.mean(PRIORITY_WEIGHT.get(r["priority"], 1) for r in g) / 4
            parts["elapsed_vs_sla"] = sum(r["x_hours"] > r["sla_hours"] for r in g) / len(g)
        elif p == "citizen_services":
            parts["elapsed_vs_sla"] = comp["late_share"]
        elif p == "environment":
            a = extra["air"]
            parts["severity"] = a["station_days_over"] / a["station_days"] if a["station_days"] else 0
        parts["independent_reports"] = comp["per_pillar"].get(p, 0) / max_c
        parts["service_criticality"] = pw.get(p, 0) / max_pw
        parts["verified_multi_zone"] = comp["zones_per_pillar"].get(p, 0) / 6
        used = sum(w[k] for k in parts)
        score = 100 * sum(w[k] * v for k, v in parts.items()) / used if used else 0
        out.append({"pillar": p, "risk_index": score, "components": parts, "weight_used_pct": used})
    return out


# ----------------------------------------------------------------------------- live view at the end of the data
def live(open_, a, d, nrw):
    as_of = datetime(2025, 12, 31, 23, 59)
    rows = []
    for r in open_:
        h = (as_of - _ts(r["opened_at"])).total_seconds() / 3600
        rate = rate_per_hour(r["category"], a, d)
        rows.append({**r, "open_hours": h, "over_sla": h > r["sla_hours"], "egp_per_hour": rate,
                     "egp_so_far": h * rate if rate is not None else None,
                     "risk_h_so_far": h * PRIORITY_WEIGHT.get(r["priority"], 1)})
    rows.sort(key=lambda r: -r["risk_h_so_far"])
    base = nrw["levels"][0]
    return {"as_of": as_of.isoformat(timespec="minutes"), "open_work_orders": rows,
            "running_loss": {"what": "Water loss at the national rate", "m3_per_day": base["lost_m3_day"],
                             "egp_per_day": base["egp_year"] / 365 if base["egp_year"] is not None else None,
                             "egp_per_second": base["egp_year"] / 365 / 86400 if base["egp_year"] is not None else None}}


# ----------------------------------------------------------------------------- main entry
def compute(write=True):
    t0 = time.time()
    a = load_assumptions()
    d = derive_from_warnings()
    closed, open_, to_be = work_orders(a, d)
    nrw = water_loss(a)
    lines, extra = as_is(a, d, to_be, nrw)
    risk = risk_index(closed, extra["complaints"], extra)
    lv = live(open_, a, d, nrw)

    money = [l["egp"] for l in lines if l["egp"] is not None]
    tgt = [r["egp_target"] for r in to_be if r["egp_target"] is not None]
    strc = [r["egp_stretch"] for r in to_be if r["egp_stretch"] is not None]
    summary = {
        "ok": True, "engine_version": ENGINE_VERSION, "computed_at": datetime.now().isoformat(timespec="seconds"),
        "dataset_label": DATASET_LABEL, "method": "rules and statistics, no trained model",
        "prices": {k: v for k, v in a.items()},
        "derived": {"leak_excess_lps": d["leak_excess_lps"], "hvac_excess_kw": d["hvac_excess_kw"],
                    "early_warning_lead_min": d["lead_min"],
                    "egp_per_hour": {c: rate_per_hour(c, a, d) for c in CATEGORY_PILLAR}},
        "totals": {"as_is_egp_priced": sum(money), "as_is_lines_priced": len(money), "as_is_lines": len(lines),
                   "to_be_egp_target": sum(tgt), "to_be_egp_stretch": sum(strc),
                   "nrw_saved_egp_target": nrw["levels"][1]["saved_egp_year"],
                   "nrw_saved_egp_stretch": nrw["levels"][2]["saved_egp_year"],
                   "saved_hours_target": sum(r["saved_h_target"] for r in to_be),
                   "saved_hours_stretch": sum(r["saved_h_stretch"] for r in to_be),
                   "work_orders_used": len(closed), "work_orders_open": len(open_)},
        "as_is": lines, "as_is_detail": extra, "to_be": to_be, "water_loss": nrw, "risk": risk, "live": lv,
        "limitations": [
            "Synthetic data: the numbers show the method, not ACUD's real costs.",
            "Water price 4.5 EGP/m3 is provisional (household top tier); the ACUD price is not published.",
            "The district has no border inflow meter, so the national water-loss rate is applied.",
            "Work orders are not linked to warnings; the early-warning gain uses the sensor's lead over the first complaint (association, not cause).",
            "Typical leak (8.15 L/s) and HVAC excess (8.30 kW) are medians over all warnings and do not size each fault.",
            "Streetlights, cameras, traffic signals, bins and complaints show hours and risk until their prices are known.",
            "The target scenario is not yet checked against team capacity.",
        ],
        "runtime_s": None,
    }
    summary["runtime_s"] = round(time.time() - t0, 1)
    if write:
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=1, default=str)
        _csv(os.path.join(OUT_DIR, "to_be_by_category.csv"), to_be)
        _csv(os.path.join(OUT_DIR, "to_be_by_workorder.csv"), closed)
        _csv(os.path.join(OUT_DIR, "as_is_by_pillar.csv"), lines)
        _csv(os.path.join(OUT_DIR, "risk_by_pillar.csv"), [{k: v for k, v in r.items() if k != "components"} for r in risk])
        _csv(os.path.join(OUT_DIR, "water_loss.csv"), nrw["levels"])
    return summary


def _csv(path, rows):
    if not rows:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})


if __name__ == "__main__":
    s = compute()
    t = s["totals"]
    print(f"done in {s['runtime_s']} s -> {SUMMARY_JSON}")
    print(f"As-Is priced: {t['as_is_egp_priced']:,.0f} EGP ({t['as_is_lines_priced']} of {t['as_is_lines']} lines have a price)")
    print(f"To-Be repair saving: target {t['to_be_egp_target']:,.0f} EGP, stretch {t['to_be_egp_stretch']:,.0f} EGP, "
          f"{t['saved_hours_target']:,.0f} fault-hours saved (target)")
    print(f"Water loss saving: 24.9%->20% {t['nrw_saved_egp_target']:,.0f} EGP/yr, ->15% {t['nrw_saved_egp_stretch']:,.0f} EGP/yr")
    for r in s["risk"]:
        print(f"  risk {r['pillar']:17} {r['risk_index']:5.1f}")
