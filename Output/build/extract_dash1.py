# -*- coding: utf-8 -*-
"""
extract_dash1.py  --  Phase A of the Oasis unified executive dashboard (dash_1.html)

Produces  Output/build/dash1_data.json  : one payload that drives the whole single-file dashboard.

Rules honoured here
  * ENE / BLD / WAT / WST  -> Gad's own `D` payload is reused verbatim (same daily series,
    same monthly arrays), so the pillar index is numerically identical to
    Gad/outputs/tables/v2_pillar_index.csv. Nothing is re-derived.
  * GCS / ENV / MOB / PSS  -> daily series built here from the prepared tables, then the
    monthly arrays are computed with the *same* mode semantics the browser engine uses.
  * Tab 2                    -> distilled from Aya's dashboard_payload.json. No detection
    logic is touched and no severity is invented (everything stays `unrated`).
  * No population denominator exists in the kit (D-06) -> every per-1,000 rate carries
    EST and the 60,000-resident Day-1 estimate is stated explicitly.

Run:  python Output/build/extract_dash1.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import warnings
from collections import Counter, OrderedDict

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)
TASKS = os.path.dirname(OUT)

BASE = os.path.join(TASKS, "Datasets", "main data", "Oasis_Service_Intelligence_FINAL",
                    "Oasis_Service_Intelligence_FINAL")
PREP = os.path.join(BASE, "data", "prepared")
SENS = os.path.join(PREP, "sensors")
KPIS = os.path.join(BASE, "evaluation", "kpis")
EARLY = os.path.join(TASKS, "Datasets", "EarlyWarnings data")
AYA = os.path.join(TASKS, "Aya", "early_warning", "outputs", "dashboard_payload.json")
GAD_HTML = os.path.join(TASKS, "Gad", "outputs", "figures",
                        "Oasis_Energy_Buildings_Dashboard_v2.html")
GAD_TABLES = os.path.join(TASKS, "Gad", "outputs", "tables")

POP_EST = 60000  # Day-1 PDF estimate, NOT in the dataset (D-06)

# --------------------------------------------------------------------------------------
# 0. calendar
# --------------------------------------------------------------------------------------
DAYS = pd.date_range("2025-01-01", "2025-12-31", freq="D")
DAY_S = [d.strftime("%Y-%m-%d") for d in DAYS]
IDX = {s: i for i, s in enumerate(DAY_S)}
MONTHS = ["2025-%02d" % m for m in range(1, 13)]
DIM = {m: int(pd.Period(m, "M").days_in_month) for m in MONTHS}
N = 365

STATUS_COLOUR = {"Normal": "#059669", "Watch": "#D97706", "Critical": "#DC2626", "n/a": "#64748B"}

PAL = dict(navy="#0F172A", navy2="#0B3C5D", teal="#0284C7", teal2="#328CC1",
           normal="#059669", watch="#D97706", critical="#DC2626", na="#64748B",
           ink="#0F172A", muted="#64748B", line="#E2E8F0")
CAT8 = ["#0284C7", "#0D9488", "#7C3AED", "#D97706", "#DC2626", "#0891B2",
        "#4F46E5", "#059669"]

SRC_NOTE = ("Synthetic — for training only | Oasis 2025 Dataset Replay | "
            "Last record: 2025-12-31")


def log(msg):
    print(msg, flush=True)


# --------------------------------------------------------------------------------------
# 1. helpers
# --------------------------------------------------------------------------------------
def ser():
    return np.zeros(N, dtype="float64")


def nan_ser():
    return np.full(N, np.nan, dtype="float64")


def to_day(s):
    """'YYYY-MM-DD...' -> day index or -1."""
    return IDX.get(str(s)[:10], -1)


def day_index_of(series):
    s = pd.to_datetime(series, errors="coerce")
    return s.dt.strftime("%Y-%m-%d").map(IDX)


def daily_count(dates):
    out = ser()
    d = pd.Series(dates).dropna()
    for k, v in d.value_counts().items():
        i = IDX.get(k)
        if i is not None:
            out[i] = float(v)
    return out


def daily_sum(df, daycol, valcol, mask=None):
    out = ser()
    d = df if mask is None else df[mask]
    g = d.groupby(daycol)[valcol].sum()
    for k, v in g.items():
        i = IDX.get(k)
        if i is not None:
            out[i] = float(v)
    return out


def daily_mean(df, daycol, valcol, mask=None):
    out = nan_ser()
    d = df if mask is None else df[mask]
    g = d.groupby(daycol)[valcol].mean()
    for k, v in g.items():
        i = IDX.get(k)
        if i is not None:
            out[i] = float(v)
    return out


def r1(v):
    return None if v is None or not np.isfinite(v) else round(float(v), 6)


def jnum(a):
    """numpy array -> JSON list with None for NaN, rounded to keep the file lean."""
    out = []
    for v in np.asarray(a, dtype="float64"):
        if not np.isfinite(v):
            out.append(None)
        else:
            out.append(round(float(v), 6))
    return out


# ---- window semantics (must mirror pilWindow in the browser engine) -------------------
def win_value(row, S, P, i0, i1):
    n = i1 - i0
    if n <= 0:
        return None
    mode = row["mode"]
    keys = row["keys"]
    if mode == "poolmed":
        vals = [v for (i, v) in P.get(row.get("pool"), []) if i0 <= i < i1]
        return float(np.median(vals)) if vals else None
    if mode == "perday":
        return float(np.nansum(S[keys[0]][i0:i1]) / n)
    if mode == "mrate":
        a = S[keys[0]][i0:i1]
        a = a[np.isfinite(a)]
        return float(np.mean(a)) if a.size else None
    if mode == "last":
        v = S[keys[0]][i1 - 1]
        return float(v) if np.isfinite(v) else None
    if mode == "perk":
        return float(np.nansum(S[keys[0]][i0:i1]) / float(row["pop"]) * 1000.0)
    A = S[keys[0]][i0:i1]
    s0 = float(np.nansum(A))
    if mode == "sum":
        return s0
    if mode == "max":
        a = A[np.isfinite(A)]
        return float(np.max(a)) if a.size else None
    B = S[keys[1]][i0:i1] if len(keys) > 1 else None
    s1 = float(np.nansum(B)) if B is not None else 0.0
    if mode == "rate":
        return s0 / s1 * 100.0 if s1 else None
    if mode == "wmean":
        return s0 / s1 if s1 else None
    if mode == "ratio":
        return s0 / (s1 * float(row.get("factor", 1.0))) * 100.0 if s1 else None
    if mode == "lf":
        a = B[np.isfinite(B)] if B is not None else np.array([])
        m1 = float(np.max(a)) if a.size else 0.0
        return (s0 * 1e3 / (n * 24.0)) / m1 * 100.0 if m1 > 0 else None
    return None


def monthly_of(row, S, P):
    out = []
    for m in MONTHS:
        i0 = IDX[m + "-01"]
        i1 = i0 + DIM[m]
        out.append(r1(win_value(row, S, P, i0, i1)))
    return out


# --------------------------------------------------------------------------------------
# 2. Gad's payload (verbatim reuse for ENE / BLD / WAT / WST)
# --------------------------------------------------------------------------------------
log("[1/7] reading Gad's v2 payload ...")
html = open(GAD_HTML, encoding="utf-8").read()
_m = html.index("const D = ")
_dec = json.JSONDecoder()
GAD, _end = _dec.raw_decode(html[_m + len("const D = "):])

S = OrderedDict()
for k, v in GAD["series"].items():
    S[k] = np.array([np.nan if x is None else float(x) for x in v], dtype="float64")
P = OrderedDict((k, [(int(a), float(b)) for a, b in v]) for k, v in GAD["pools"].items())
log("      %d daily series, %d pool(s) reused" % (len(S), len(P)))

PILLARS = OrderedDict()
for p in GAD["pillars"]:
    PILLARS[p["pillar"]] = [dict(r) for r in p["rows"]]

# --------------------------------------------------------------------------------------
# 3. service requests  ->  GCS / MOB / ENV volume + resolution pools
# --------------------------------------------------------------------------------------
log("[2/7] service_requests ...")
sr = pd.read_csv(os.path.join(PREP, "service_requests_prepared.csv"), encoding="utf-8-sig",
                 usecols=["request_id", "created_local", "channel", "zone_id", "category",
                          "pillar_provisional", "status", "resolution_hours", "is_open",
                          "satisfaction_1_5", "is_post_app_launch"])
sr["d"] = sr["created_local"].astype(str).str[:10]
sr = sr[sr["d"].isin(IDX)]

ch = sr["channel"].fillna("unknown")
S["gcs_all"] = daily_count(sr["d"])
S["gcs_app"] = daily_count(sr.loc[ch == "app", "d"])
S["gcs_na"] = daily_count(sr.loc[ch != "app", "d"])

for pid, key in [("energy", "pv_energy"), ("buildings", "pv_buildings"),
                 ("water", "pv_water"), ("waste", "pv_waste"),
                 ("citizen_services", "pv_gcs"), ("environment", "pv_env"),
                 ("mobility", "pv_mob"), ("public_safety", "pv_pss")]:
    S[key] = daily_count(sr.loc[sr["pillar_provisional"] == pid, "d"])

S["env_req"] = daily_count(sr.loc[sr["pillar_provisional"] == "environment", "d"])
S["mob_req"] = daily_count(sr.loc[sr["pillar_provisional"] == "mobility", "d"])
S["mob_na"] = daily_count(sr.loc[(sr["pillar_provisional"] == "mobility") & (ch != "app"), "d"])
S["pss_req"] = daily_count(sr.loc[sr["pillar_provisional"] == "public_safety", "d"])

# app share per day (only meaningful after the June launch; kept as a rate over sums)
S["gcs_app_share"] = np.where(S["gcs_all"] > 0, S["gcs_app"] / np.maximum(S["gcs_all"], 1) * 100.0, np.nan)

def pool_from(df, mask=None):
    d = df if mask is None else df[mask]
    d = d[np.isfinite(d["resolution_hours"])]
    di = d["d"].map(IDX)
    return [[int(i), round(float(v), 2)] for i, v in zip(di, d["resolution_hours"]) if pd.notna(i)]

P["gcs_res"] = pool_from(sr)
P["mob_res"] = pool_from(sr, sr["pillar_provisional"] == "mobility")
log("      gcs_res=%d pairs, mob_res=%d pairs" % (len(P["gcs_res"]), len(P["mob_res"])))

# per-pillar resolution table (for the GCS dumbbell, cohort trend, backlog lines)
k23 = pd.read_csv(os.path.join(KPIS, "k02_k03_resolution_month_pillar.csv"), encoding="utf-8-sig")
k01 = pd.read_csv(os.path.join(KPIS, "k01_complaint_volume_month_pillar_channel.csv"), encoding="utf-8-sig")
k04d = pd.read_csv(os.path.join(KPIS, "k04_open_backlog_daily.csv"), encoding="utf-8-sig")
k04m = pd.read_csv(os.path.join(KPIS, "k04_open_backlog_month_end_pillar.csv"), encoding="utf-8-sig")
k05 = pd.read_csv(os.path.join(KPIS, "k05_work_order_sla_month_asset_class.csv"), encoding="utf-8-sig")

k04d["d"] = k04d["date"].astype(str).str[:10]
S["gcs_backlog"] = np.array(
    [float(k04d.loc[k04d["d"] == d, "open_backlog_end_of_day"].iloc[0])
     if (k04d["d"] == d).any() else np.nan for d in DAY_S], dtype="float64")

# --------------------------------------------------------------------------------------
# 4. gov services -> GCS-05/06 weighted processing days
# --------------------------------------------------------------------------------------
log("[3/7] gov_services ...")
gov = pd.read_csv(os.path.join(EARLY, "01_CLEAN_SOURCE_CSV", "gov_services.csv"), encoding="utf-8-sig")
gov["d"] = gov["date"].astype(str).str[:10]
gov["w"] = gov["transactions"] * gov["avg_processing_days"]
S["gov_tx"] = daily_sum(gov, "d", "transactions")
S["gov_daysw"] = daily_sum(gov, "d", "w")
gov_by_type = (gov.groupby("service_type")
               .apply(lambda g: pd.Series({"tx": g["transactions"].sum(),
                                           "days": (g["transactions"] * g["avg_processing_days"]).sum()}),
                      include_groups=False)
               .reset_index())
gov_by_type["wmean"] = gov_by_type["days"] / gov_by_type["tx"]

# --------------------------------------------------------------------------------------
# 5. incidents -> PSS
# --------------------------------------------------------------------------------------
log("[4/7] incidents ...")
inc = pd.read_csv(os.path.join(PREP, "incidents_prepared.csv"), encoding="utf-8-sig",
                  usecols=["incident_id", "timestamp", "zone_id", "type", "severity", "source",
                           "response_min", "status", "ingested_at", "ingest_lag_min"])
inc["d"] = inc["timestamp"].astype(str).str[:10]
inc = inc[inc["d"].isin(IDX)]
inc["sev"] = inc["severity"].astype(int)

S["inc_n"] = daily_count(inc["d"])
S["inc_s12"] = daily_count(inc.loc[inc["sev"].isin([1, 2]), "d"])
S["inc_late"] = daily_count(inc.loc[inc["ingest_lag_min"] > 1440, "d"])

def inc_pool(mask=None):
    d = inc if mask is None else inc[mask]
    di = d["d"].map(IDX)
    return [[int(i), round(float(v), 1)] for i, v in zip(di, d["response_min"])
            if pd.notna(i) and np.isfinite(v)]

P["pss_s12"] = inc_pool(inc["sev"].isin([1, 2]))
for sv in (1, 2, 3, 4):
    P["pss_s%d" % sv] = inc_pool(inc["sev"] == sv)

# --------------------------------------------------------------------------------------
# 6. sensors
# --------------------------------------------------------------------------------------
log("[5/7] sensors ...")
# ---- air quality
aq = pd.read_csv(os.path.join(SENS, "air_quality_prepared.csv.gz"), encoding="utf-8-sig",
                 usecols=["station_id", "ts_local", "pm25", "pm10", "no2", "o3", "temp_c", "humidity_pct"])
aq["ts"] = pd.to_datetime(aq["ts_local"], errors="coerce")
aq["d"] = aq["ts"].dt.strftime("%Y-%m-%d")
aq["h"] = aq["ts"].dt.hour
aq = aq[aq["d"].isin(IDX)]
S["pm10_d"] = daily_mean(aq, "d", "pm10")
S["pm25_d"] = daily_mean(aq, "d", "pm25")
S["dust_d"] = np.where(np.nan_to_num(S["pm10_d"], nan=0.0) >= 150.0, 1.0, 0.0)
aq_hour = aq.groupby("h")[["pm10", "pm25", "no2", "o3", "temp_c", "humidity_pct"]].mean()

# ---- noise (night window 23:00-06:59)
nz = pd.read_csv(os.path.join(SENS, "noise_prepared.csv.gz"), encoding="utf-8-sig",
                 usecols=["sensor_id", "ts_local", "laeq_db"])
nz["ts"] = pd.to_datetime(nz["ts_local"], errors="coerce")
nz["d"] = nz["ts"].dt.strftime("%Y-%m-%d")
nz["h"] = nz["ts"].dt.hour
nz["wd"] = nz["ts"].dt.dayofweek
nz = nz[nz["d"].isin(IDX)]
night = nz[(nz["h"] >= 23) | (nz["h"] <= 6)]
S["noise_night_d"] = daily_mean(night, "d", "laeq_db")
S["noise_exc_h"] = daily_count(night.loc[night["laeq_db"] > 55, "d"])
noise_heat = night.pivot_table(index="wd", columns="h", values="laeq_db", aggfunc="mean")
noise_month = (night.assign(m=night["ts"].dt.strftime("%Y-%m"))
               .groupby(["sensor_id", "m"])["laeq_db"].mean().unstack())

# ---- traffic
tf = pd.read_csv(os.path.join(SENS, "traffic_counts_prepared.csv.gz"), encoding="utf-8-sig",
                 usecols=["sensor_id", "ts_local", "vehicle_count", "avg_speed_kmh", "occupancy_pct"])
tf["ts"] = pd.to_datetime(tf["ts_local"], errors="coerce")
tf["d"] = tf["ts"].dt.strftime("%Y-%m-%d")
tf["h"] = tf["ts"].dt.hour
tf["wd"] = tf["ts"].dt.dayofweek
tf = tf[tf["d"].isin(IDX)]
ff = tf[(tf["h"] <= 5)]["avg_speed_kmh"]
freeflow = float(np.nanpercentile(ff, 85))
peak = tf[((tf["h"] >= 7) & (tf["h"] <= 10)) | ((tf["h"] >= 15) & (tf["h"] <= 19))]
cong = peak.groupby("d")["avg_speed_kmh"].median() / freeflow
S["cong_d"] = np.array([float(cong.get(d, np.nan)) for d in DAY_S])
tf_hour = tf.groupby("h")["avg_speed_kmh"].agg(
    p20=lambda x: np.nanpercentile(x, 20), med="median",
    p95=lambda x: np.nanpercentile(x, 95))

# ---- transit
tr = pd.read_csv(os.path.join(SENS, "transit_ridership_prepared.csv"), encoding="utf-8-sig",
                 usecols=["date", "line_id", "stop_id", "boardings", "on_time_pct"])
tr["d"] = tr["date"].astype(str).str[:10]
tr = tr[tr["d"].isin(IDX)]
tr["w"] = tr["boardings"] * tr["on_time_pct"]
ot = tr.groupby("d").apply(lambda g: g["w"].sum() / max(g["boardings"].sum(), 1), include_groups=False)
S["transit_ot"] = np.array([float(ot.get(d, np.nan)) for d in DAY_S])
S["transit_board"] = daily_sum(tr, "d", "boardings")
tr_line = tr.groupby("line_id").apply(
    lambda g: pd.Series({"boardings": g["boardings"].sum(),
                         "ontime": g["w"].sum() / max(g["boardings"].sum(), 1),
                         "stops": g["stop_id"].nunique()}), include_groups=False).reset_index()

# ---- parking
pk = pd.read_csv(os.path.join(SENS, "parking_occupancy_prepared.csv.gz"), encoding="utf-8-sig",
                 usecols=["lot_id", "ts_local", "capacity", "occupied"])
pk["ts"] = pd.to_datetime(pk["ts_local"], errors="coerce")
pk["d"] = pk["ts"].dt.strftime("%Y-%m-%d")
pk = pk[pk["d"].isin(IDX)]
pk["sat"] = (pk["occupied"] >= pk["capacity"]).astype(float)
S["park_sat"] = daily_mean(pk, "d", "sat")
S["park_sat"] = np.where(np.isfinite(S["park_sat"]), S["park_sat"] * 100.0, np.nan)
pk_lot = pk.groupby("lot_id").agg(cap=("capacity", "max"), sat=("sat", "mean"),
                                  occ=("occupied", "mean")).reset_index()
pk_lot["sat"] = pk_lot["sat"] * 100.0
pk_lot["util"] = pk_lot["occ"] / pk_lot["cap"] * 100.0

# ---- cameras
cam = pd.read_csv(os.path.join(SENS, "camera_status_prepared.csv"), encoding="utf-8-sig",
                  usecols=["camera_id", "date", "uptime_pct"])
cam["d"] = cam["date"].astype(str).str[:10]
cam = cam[cam["d"].isin(IDX)]
p5 = float(np.nanpercentile(cam["uptime_pct"], 5))
S["cam_up"] = daily_mean(cam, "d", "uptime_pct")
S["cam_low"] = daily_count(cam.loc[cam["uptime_pct"] < p5, "d"])
cam_day = cam.groupby("d")["uptime_pct"].mean()
cam_day_n = cam.groupby("d")["uptime_pct"].apply(lambda x: int((x < p5).sum()))

# ---- streetlights (already in Gad's series, need per-month fault counts for the chart)
sl = pd.read_csv(os.path.join(SENS, "streetlights_prepared.csv.gz"), encoding="utf-8-sig",
                 usecols=["asset_id", "date", "status", "burn_hours"])
sl["d"] = sl["date"].astype(str).str[:10]
sl = sl[sl["d"].isin(IDX)]
sl["m"] = sl["d"].str[:7]
sl_m = sl.pivot_table(index="m", columns="status", values="asset_id", aggfunc="count").fillna(0)

# ---- bin fill (hour-of-day profile + per-route tonnage comes from trips)
bf = pd.read_csv(os.path.join(SENS, "bin_fill_prepared.csv.gz"), encoding="utf-8-sig",
                 usecols=["bin_id", "ts_local", "fill_pct"])
bf["ts"] = pd.to_datetime(bf["ts_local"], errors="coerce")
bf["h"] = bf["ts"].dt.hour
bf["d"] = bf["ts"].dt.strftime("%Y-%m-%d")
bf = bf[bf["d"].isin(IDX)]
bf_hour = bf.groupby("h")["fill_pct"].agg(med="median",
                                          p90=lambda x: np.nanpercentile(x, 90),
                                          over=lambda x: (x >= 95).mean() * 100.0)

# ---- trips
tp = pd.read_csv(os.path.join(PREP, "collection_trips_prepared.csv"), encoding="utf-8-sig",
                 usecols=["trip_id", "truck_id", "route_id", "tonnes", "bins_collected",
                          "duration_hours", "date_local"])
tp_route = tp.groupby("route_id").agg(tonnes=("tonnes", "sum"), trips=("trip_id", "count"),
                                      bins=("bins_collected", "sum")).reset_index().sort_values("tonnes")

# ---- water: pressure per sensor, quality, building use
prs = pd.read_csv(os.path.join(SENS, "network_pressure_prepared.csv.gz"), encoding="utf-8-sig",
                  usecols=["sensor_id", "ts_local", "pressure_bar"])
prs["ts"] = pd.to_datetime(prs["ts_local"], errors="coerce")
prs["d"] = prs["ts"].dt.strftime("%Y-%m-%d")
prs = prs[prs["d"].isin(IDX)]
prs_sensor = prs.groupby("sensor_id")["pressure_bar"].agg(
    med="median", p01=lambda x: np.nanpercentile(x, 1), p99=lambda x: np.nanpercentile(x, 99))

wq = pd.read_csv(os.path.join(SENS, "water_quality_prepared.csv"), encoding="utf-8-sig")
wq_n = int(((wq["turbidity_ntu"] > 5) | (wq["chlorine_mg_l"] < 0.2)).sum())

wm = pd.read_csv(os.path.join(SENS, "water_meters_prepared.csv.gz"), encoding="utf-8-sig",
                 usecols=["building_id", "timestamp", "m3"])
wm_b = wm.groupby("building_id")["m3"].sum().sort_values(ascending=False)

em = pd.read_csv(os.path.join(SENS, "electricity_meters_prepared.csv.gz"), encoding="utf-8-sig",
                 usecols=["building_id", "timestamp", "kwh"])
em_b = em.groupby("building_id")["kwh"].sum().sort_values(ascending=False)
del em, wm, prs, bf, tf, aq, nz, sl

# ---- work orders
wo = pd.read_csv(os.path.join(PREP, "work_orders_prepared.csv"), encoding="utf-8-sig",
                 usecols=["work_order_id", "asset_prefix", "asset_class", "opened_at", "closed_at",
                          "priority", "sla_status_native", "duration_hours"])
wo["d"] = wo["opened_at"].astype(str).str[:10]
wo["m"] = wo["d"].str[:7]

def wo_rate(prefix, num_status):
    on = daily_count(wo.loc[(wo["asset_prefix"] == prefix) &
                            (wo["sla_status_native"].isin(num_status)), "d"])
    al = daily_count(wo.loc[wo["asset_prefix"] == prefix, "d"])
    return on, al

S["tsg_on"], S["tsg_n"] = wo_rate("TSG", ["met"])
S["cam_on"], S["cam_n"] = wo_rate("CAM", ["met"])
P["cam_res"] = [[int(i), round(float(v), 2)] for i, v in
                zip(wo.loc[wo["asset_prefix"] == "CAM", "d"].map(IDX),
                    wo.loc[wo["asset_prefix"] == "CAM", "duration_hours"])
                if pd.notna(i) and np.isfinite(v)]

# --------------------------------------------------------------------------------------
# 7. pillar rows
# --------------------------------------------------------------------------------------
log("[6/7] pillar rows ...")

def row(kpi, label, unit, dec, better, mode, keys, note, flow=False, factor=1.0,
        pool=None, pop=None):
    r = dict(kpi=kpi, label=label, unit=unit, dec=dec, better=better, mode=mode,
             keys=keys, pool=pool, factor=factor, flow=flow, note=note)
    if pop is not None:
        r["pop"] = pop
    r["monthly"] = monthly_of(r, S, P)
    return r


GCS_ROWS = [
    row("GCS-01", "App channel share", "%", 1, "high", "rate", ["gcs_app", "gcs_all"],
        "app ÷ all requests in the window — 0 % before the June 2025 launch (DQ-10)"),
    row("ALL-01/06", "Non-app requests", "requests", 0, "low", "sum", ["gcs_na"],
        "call centre + service centre only — the counter channel", flow=True),
    row("ALL-03", "Median resolution", "h", 1, "low", "poolmed", [],
        "true request-level median, 44,817 closed requests, no approved SLA (D-04)", pool="gcs_res"),
    row("ALL-05", "Open backlog", "requests", 0, "low", "last", ["gcs_backlog"],
        "open at the last day of the window — December is an incomplete cohort (DQ-11)"),
    row("GCS-05/06", "Gov processing days", "days", 2, "low", "wmean", ["gov_daysw", "gov_tx"],
        "transaction-weighted mean of the 5 government services"),
]

ENV_ROWS = [
    row("ENV-01", "District mean PM10", "\u00b5g/m\u00b3", 1, "low", "mrate", ["pm10_d"],
        "mean of the 8 monitoring stations, per day"),
    row("ENV-02", "Dust days", "days", 0, "low", "sum", ["dust_d"],
        "district daily mean PM10 \u2265 150 \u00b5g/m\u00b3", flow=True),
    row("ENV-03", "Mean PM2.5", "\u00b5g/m\u00b3", 1, "low", "mrate", ["pm25_d"],
        "station network daily mean, averaged over the window"),
    row("ENV-04", "Night noise LAeq", "dB", 1, "low", "mrate", ["noise_night_d"],
        "23:00–07:00 mean of 10 sensors"),
    row("ENV-05", "Night exceedance", "sensor-h/day", 2, "low", "perday", ["noise_exc_h"],
        "night sensor-hours above 55 dB, divided by the window length"),
    row("ALL-01 [ENV]", "Environment requests", "requests", 0, "low", "sum", ["env_req"],
        "noise, cleanliness and green-space complaints", flow=True),
]

MOB_ROWS = [
    row("MOB-01", "Congestion index", "ratio", 3, "high", "mrate", ["cong_d"],
        "peak-window median speed ÷ free-flow P85 of 00–05 (higher = freer flow)"),
    row("ALL-01 [MOB]", "Traffic requests", "requests", 0, "low", "sum", ["mob_req"],
        "roads, parking and signal complaints", flow=True),
    row("ALL-06 [MOB]", "Non-app requests", "requests", 0, "low", "sum", ["mob_na"],
        "call centre + service centre only", flow=True),
    row("ALL-02 [MOB]", "Requests / 1,000", "per 1,000 (EST)", 1, "low", "perk", ["mob_req"],
        "denominator is the ~60,000 Day-1 estimate, not in the kit (D-06)", flow=True, pop=POP_EST),
    row("ALL-03 [MOB]", "Median resolution", "h", 1, "low", "poolmed", [],
        "request-level median for the mobility pillar", pool="mob_res"),
    row("ALL-07 [TSG]", "Signal WO on-SLA", "%", 1, "high", "rate", ["tsg_on", "tsg_n"],
        "native sla_hours on traffic-signal work orders, closed only"),
    row("TRANSIT-ONTIME", "Transit on-time", "%", 1, "high", "mrate", ["transit_ot"],
        "boardings-weighted daily on-time share, 3 lines"),
    row("PARK-SAT", "Parking saturation", "%", 1, "low", "mrate", ["park_sat"],
        "lot-hours at 100 % occupancy, 12 lots (DQ-21: profile groups, not zones)"),
]

PSS_ROWS = [
    row("PSS-01", "Incident volume", "incidents", 0, "low", "sum", ["inc_n"],
        "9 incident types, all severities", flow=True),
    row("PSS-02", "Incidents / 1,000", "per 1,000 (EST)", 1, "low", "perk", ["inc_n"],
        "denominator is the ~60,000 Day-1 estimate, not in the kit (D-06)", flow=True, pop=POP_EST),
    row("PSS-03", "Critical share", "%", 1, "low", "rate", ["inc_s12", "inc_n"],
        "severity 1–2 (fire alarm, medical emergency, accident)"),
    row("PSS-04", "Median response s1–s2", "min", 1, "low", "poolmed", [],
        "critical-severity response median, request level", pool="pss_s12"),
    row("PSS-06", "Late-ingested", "%", 2, "low", "rate", ["inc_late", "inc_n"],
        "incidents logged more than 24 h after the event"),
    row("PSS-07", "Camera availability", "%", 1, "high", "mrate", ["cam_up"],
        "mean daily uptime of 60 cameras"),
    row("PSS-08", "Low-uptime camera-days", "camera-days", 0, "low", "sum", ["cam_low"],
        "camera-days below the fleet P5 uptime", flow=True),
    row("ALL-07 [CAM]", "CCTV WO on-SLA", "%", 1, "high", "rate", ["cam_on", "cam_n"],
        "native sla_hours on CCTV work orders, closed only"),
    row("ALL-08 [CAM]", "Camera repair time", "h", 1, "low", "poolmed", [],
        "median hours to close a camera work order", pool="cam_res"),
]

PILLARS["GCS"] = GCS_ROWS
PILLARS["ENV"] = ENV_ROWS
PILLARS["MOB"] = MOB_ROWS
PILLARS["PSS"] = PSS_ROWS

PILLAR_META = [
    ("ENE", "Energy", "v2_p01_energy_index", "Gad"),
    ("BLD", "Buildings & HVAC", "v2_p02_buildings_index", "Gad"),
    ("WAT", "Water Network", "v2_p03_water_index", "Gad"),
    ("WST", "Waste Management", "v2_p04_waste_index", "Gad"),
    ("GCS", "Gov & Citizen Services", "d1_p05_gcs_index", "Aisha"),
    ("ENV", "Environment", "d1_p06_env_index", "Aisha"),
    ("MOB", "Mobility & Traffic", "d1_p07_mob_index", "Ayat"),
    ("PSS", "Public Safety", "d1_p08_pss_index", "Ayat"),
]
PILLARS_OUT = [dict(id=pid, pillar=code, name=name, owner=owner, rows=PILLARS[code])
               for code, name, pid, owner in PILLAR_META]

ANNUAL = {}
for code, name, pid, owner in PILLAR_META:
    for r in PILLARS[code]:
        v = win_value(r, S, P, 0, N)
        ANNUAL["%s:%s" % (code, r["kpi"])] = r1(v)

# --------------------------------------------------------------------------------------
# 8. charts
# --------------------------------------------------------------------------------------
log("[7/7] charts ...")
FONT = "Inter, 'Plus Jakarta Sans', 'Segoe UI', system-ui, sans-serif"


def base_layout(height=300, showlegend=True, **kw):
    lay = {
        "template": "plotly_white",
        "font": {"family": FONT, "size": 11.5, "color": PAL["ink"]},
        "margin": {"l": 58, "r": 20, "t": 10, "b": 46},
        "height": height,
        "hovermode": "x unified",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "paper_bgcolor": "rgba(0,0,0,0)",
        "showlegend": showlegend,
        "legend": {"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0,
                   "font": {"size": 10}, "bgcolor": "rgba(0,0,0,0)"},
        "xaxis": {"showgrid": False, "zeroline": False, "linecolor": "#E2E8F0",
                  "tickfont": {"size": 10, "color": "#94A3B8"}},
        "yaxis": {"showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}},
        "hoverlabel": {"font": {"size": 11, "family": FONT}},
    }
    lay.update(kw)
    return lay


def mk(traces, layout, time=False, axes=None):
    return {"data": traces, "layout": layout, "time": bool(time),
            "axes": axes or (["xaxis"] if time else [])}


def line(x, y, name, colour, width=2.0, dash=None, fill=None, mode="lines",
         hovertemplate=None, yaxis=None, opacity=1.0, shape=None):
    t = {"type": "scatter", "mode": mode, "x": x, "y": y, "name": name,
         "line": {"color": colour, "width": width, "shape": shape or "linear"},
         "opacity": opacity,
         "hovertemplate": hovertemplate or ("<b>%{y:,.2f}</b> · " + name + "<extra></extra>")}
    if dash:
        t["line"]["dash"] = dash
    if fill:
        t["fill"] = fill
        t["fillcolor"] = fill if fill.startswith("rgba") else colour
    if yaxis:
        t["yaxis"] = yaxis
    return t


def bar(x, y, name, colour, yaxis=None, text=None, hovertemplate=None):
    t = {"type": "bar", "x": x, "y": y, "name": name,
         "marker": {"color": colour, "line": {"color": "rgba(255,255,255,.85)", "width": 1}},
         "hovertemplate": hovertemplate or ("<b>%{y:,.2f}</b> · " + name + "<extra></extra>")}
    if yaxis:
        t["yaxis"] = yaxis
    if text is not None:
        t["text"] = text
        t["textposition"] = "outside"
        t["textfont"] = {"size": 9.5, "color": "#475569"}
    return t


def cat_layout(lay, cats, tickangle=-20):
    lay["xaxis"]["type"] = "category"
    lay["xaxis"]["tickangle"] = tickangle
    lay["xaxis"]["categoryorder"] = "array"
    lay["xaxis"]["categoryarray"] = cats
    return lay


SPECS = OrderedDict()
MLAB = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MLAB2 = ["%s %s" % (m[5:], "") for m in MONTHS]
SHORTM = [d.strftime("%b") for d in pd.to_datetime([m + "-01" for m in MONTHS])]

# ---------- cross-pillar overview ----------
pv_keys = ["pv_energy", "pv_buildings", "pv_water", "pv_waste", "pv_gcs", "pv_env", "pv_mob", "pv_pss"]
pv_names = ["Energy", "Buildings", "Water", "Waste", "Gov & Citizen", "Environment",
            "Mobility", "Public Safety"]
cum = [np.cumsum(np.nan_to_num(S[k])) for k in pv_keys]
SPECS["ov_pillar_volume"] = mk(
    [line(DAY_S, c, pv_names[i], CAT8[i], width=0.0, fill="tozeroy", opacity=0.55)
     for i, c in enumerate(cum)],
    base_layout(310, True, yaxis={"title": {"text": "cumulative requests", "font": {"size": 10}},
                                 "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                 "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}},
                hovermode="x unified", legend={"orientation": "h", "yanchor": "bottom", "y": 1.02,
                                               "x": 0, "font": {"size": 10}}),
    time=True)

tot = S["gcs_all"]
SPECS["ov_app_share"] = mk(
    [bar(DAY_S, tot, "All requests", "rgba(148,163,184,.45)", hovertemplate="%{y} requests<extra></extra>"),
     line(DAY_S, S["gcs_app_share"], "App share %", PAL["teal"], width=1.6, yaxis="y2",
          hovertemplate="<b>%{y:.1f}%</b> app share<extra></extra>")],
    base_layout(280, True,
                yaxis={"showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                       "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}},
                yaxis2={"overlaying": "y", "side": "right", "range": [0, 100],
                        "ticksuffix": "%", "showgrid": False, "zeroline": False,
                        "tickfont": {"size": 10, "color": PAL["teal"]}}),
    time=True)

# ---------- ENE ----------
SPECS["ene_month_cons"] = mk(
    [bar(SHORTM, [float(x) for x in PILLARS["ENE"][0]["monthly"]], "Cleaned GWh", PAL["navy2"]),
     line(SHORTM, [float(x) for x in PILLARS["ENE"][0]["monthly"]], "", PAL["navy2"],
          mode="markers+lines", width=0)],
    cat_layout(base_layout(280, False,
                           yaxis={"title": {"text": "GWh", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}}),
               SHORTM, 0))

SPECS["ene_peak_lf"] = mk(
    [line(SHORTM, [float(x) for x in PILLARS["ENE"][1]["monthly"]], "Peak MWh/h", PAL["watch"],
          width=2, mode="lines+markers"),
     line(SHORTM, [float(x) for x in PILLARS["ENE"][2]["monthly"]], "Load factor %", PAL["teal"],
          width=2, mode="lines+markers", yaxis="y2")],
    cat_layout(base_layout(280, True,
                           yaxis={"title": {"text": "MWh/h", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}},
                           yaxis2={"overlaying": "y", "side": "right", "ticksuffix": "%",
                                   "showgrid": False, "zeroline": False,
                                   "tickfont": {"size": 10, "color": PAL["teal"]}}),
               SHORTM, 0))

em_top = em_b.head(10)[::-1]
SPECS["ene_buildings"] = mk(
    [bar(list(em_top.index), [round(float(v) / 1000.0, 1) for v in em_top.values],
         "MWh (raw meter)", PAL["teal"],
         hovertemplate="%{y:,.1f} MWh<extra></extra>")],
    cat_layout(base_layout(300, False,
                           xaxis={"showgrid": False, "zeroline": False, "linecolor": "#E2E8F0",
                                  "tickfont": {"size": 9.6, "color": "#94A3B8"}},
                           yaxis={"title": {"text": "MWh / year", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}}),
               list(em_top.index), -40))

slf = [float(sl_m.loc[m, "fault"]) if m in sl_m.index and "fault" in sl_m.columns else 0.0 for m in MONTHS]
slt = [float(sl_m.loc[m].sum()) if m in sl_m.index else 0.0 for m in MONTHS]
SPECS["ene_streetlight"] = mk(
    [bar(SHORTM, [round(a / b * 100, 2) if b else 0 for a, b in zip(slf, slt)], "Fault lamp-days %",
         PAL["critical"], hovertemplate="%{y:.2f} %<extra></extra>"),
     line(SHORTM, [float(x) for x in PILLARS["ENE"][3]["monthly"]], "Outages · non-app",
          PAL["muted"], width=1.8, mode="lines+markers", yaxis="y2")],
    cat_layout(base_layout(280, True,
                           yaxis={"title": {"text": "% of lamp-days", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}},
                           yaxis2={"overlaying": "y", "side": "right", "showgrid": False,
                                   "zeroline": False, "tickfont": {"size": 10, "color": PAL["muted"]}}),
               SHORTM, 0))

# ---------- BLD ----------
bms = pd.read_csv(os.path.join(GAD_TABLES, "bms_sensor_health.csv"), encoding="utf-8-sig")
bms = bms.sort_values("hot_hours")
SPECS["bld_hot"] = mk(
    [bar(list(bms["building_id"]), list(bms["hot_hours"].astype(float)), "Hours > 45 °C",
         [PAL["critical"] if f else PAL["teal2"] for f in bms["flagged"]],
         hovertemplate="%{y:,.0f} h above 45 °C<extra></extra>")],
    cat_layout(base_layout(290, False,
                           yaxis={"title": {"text": "hours", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}}),
               list(bms["building_id"]), -55))

SPECS["bld_hvac"] = mk(
    [bar(SHORTM, [float(x) for x in PILLARS["BLD"][0]["monthly"]], "HVAC share %", PAL["watch"],
         hovertemplate="%{y:.2f} %<extra></extra>"),
     line(SHORTM, [float(x) for x in PILLARS["BLD"][3]["monthly"]], "Comfort exceedance %",
          PAL["critical"], width=1.8, mode="lines+markers", yaxis="y2")],
    cat_layout(base_layout(280, True,
                           yaxis={"title": {"text": "HVAC share %", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}},
                           yaxis2={"overlaying": "y", "side": "right", "ticksuffix": "%",
                                   "showgrid": False, "zeroline": False,
                                   "tickfont": {"size": 10, "color": PAL["critical"]}}),
               SHORTM, 0))

bms2 = bms.sort_values("valid_rate_pct")
SPECS["bld_valid"] = mk(
    [bar(list(bms2["building_id"]), list(bms2["valid_rate_pct"].astype(float)), "Valid hours %",
         [PAL["critical"] if f else PAL["normal"] for f in bms2["flagged"]],
         hovertemplate="%{y:.1f} %<extra></extra>")],
    cat_layout(base_layout(290, False,
                           yaxis={"title": {"text": "% valid", "font": {"size": 10}},
                                  "range": [0, 105], "showgrid": True, "gridcolor": "#E8EEF4",
                                  "griddash": "dot", "zeroline": False,
                                  "tickfont": {"size": 10, "color": "#94A3B8"}}),
               list(bms2["building_id"]), -55))

hv = k05[k05["asset_class"] == "hvac_unit"].groupby("month")[["work_orders", "met", "breached"]].sum()
SPECS["bld_sla"] = mk(
    [bar(SHORTM, [int(hv.loc[m, "met"]) if m in hv.index else 0 for m in MONTHS], "Met", PAL["normal"],
         hovertemplate="%{y} work orders<extra></extra>"),
     bar(SHORTM, [int(hv.loc[m, "breached"]) if m in hv.index else 0 for m in MONTHS], "Breached",
         PAL["critical"], hovertemplate="%{y} work orders<extra></extra>")],
    cat_layout(base_layout(270, True, barmode="stack",
                           yaxis={"title": {"text": "work orders", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}}),
               SHORTM, 0))

# ---------- WAT ----------
SPECS["wat_anomaly"] = mk(
    [bar(SHORTM, [float(x) for x in PILLARS["WAT"][1]["monthly"]], "Anomaly sensor-days",
         PAL["watch"], hovertemplate="%{y:,.0f} sensor-days<extra></extra>"),
     line(SHORTM, [float(x) for x in PILLARS["WAT"][2]["monthly"]], "Pressure in band %",
          PAL["teal"], width=1.8, mode="lines+markers", yaxis="y2")],
    cat_layout(base_layout(280, True,
                           yaxis={"title": {"text": "sensor-days", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}},
                           yaxis2={"overlaying": "y", "side": "right", "range": [90, 100],
                                   "ticksuffix": "%", "showgrid": False, "zeroline": False,
                                   "tickfont": {"size": 10, "color": PAL["teal"]}}),
               SHORTM, 0))

wat01 = np.array([v for _, v in P["wat01"]])
edges = [0, 6, 12, 18, 24, 36, 48, 72, 120, 400]
hist, _ = np.histogram(wat01, bins=edges)
labels = ["0–6", "6–12", "12–18", "18–24", "24–36", "36–48", "48–72", "72–120", "120+"]
SPECS["wat_resolution"] = mk(
    [bar(labels, [int(h) for h in hist], "Outage requests", PAL["teal2"],
         hovertemplate="%{y:,} requests<extra></extra>")],
    cat_layout(base_layout(280, False,
                           xaxis={"showlegend": False},
                           yaxis={"title": {"text": "requests", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}}),
               labels, 0))

wmt = wm_b.head(10)[::-1]
SPECS["wat_buildings"] = mk(
    [bar(list(wmt.index), [round(float(v) / 1000.0, 1) for v in wmt.values], "thousand m³",
         PAL["teal"], hovertemplate="%{y:,.1f} thousand m³<extra></extra>")],
    cat_layout(base_layout(300, False,
                           yaxis={"title": {"text": "thousand m³ / year", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}}),
               list(wmt.index), -40))

vw = k05[k05["asset_class"].isin(["valve", "pump"])].groupby("month")[["work_orders", "met", "breached"]].sum()
SPECS["wat_sla"] = mk(
    [bar(SHORTM, [int(vw.loc[m, "met"]) if m in vw.index else 0 for m in MONTHS], "Met", PAL["normal"],
         hovertemplate="%{y} work orders<extra></extra>"),
     bar(SHORTM, [int(vw.loc[m, "breached"]) if m in vw.index else 0 for m in MONTHS], "Breached",
         PAL["critical"], hovertemplate="%{y} work orders<extra></extra>")],
    cat_layout(base_layout(270, True, barmode="stack",
                           yaxis={"title": {"text": "work orders", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}}),
               SHORTM, 0))

# ---------- WST ----------
SPECS["wst_overflow"] = mk(
    [line(SHORTM, [float(x) for x in PILLARS["WST"][0]["monthly"]], "Overflow at 06:00 %",
          PAL["watch"], width=2, mode="lines+markers"),
     line(SHORTM, [float(x) for x in PILLARS["WST"][1]["monthly"]], "Readings ≥ 95 %",
          PAL["critical"], width=1.8, mode="lines+markers", dash="dot")],
    cat_layout(base_layout(280, True,
                           yaxis={"title": {"text": "% (share, never mean fill — DQ-18)",
                                            "font": {"size": 9.5}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}}),
               SHORTM, 0))

SPECS["wst_throughput"] = mk(
    [bar(SHORTM, [float(x) for x in PILLARS["WST"][3]["monthly"]], "t / day", PAL["teal"],
         hovertemplate="%{y:.2f} t/day<extra></extra>"),
     line(SHORTM, [float(x) for x in PILLARS["WST"][2]["monthly"]], "Trips / day", PAL["navy2"],
          width=1.8, mode="lines+markers", yaxis="y2")],
    cat_layout(base_layout(280, True,
                           yaxis={"title": {"text": "t / day", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}},
                           yaxis2={"overlaying": "y", "side": "right", "showgrid": False,
                                   "zeroline": False, "tickfont": {"size": 10, "color": PAL["navy2"]}}),
               SHORTM, 0))

SPECS["wst_hour"] = mk(
    [line(list(range(24)), [float(bf_hour.loc[h, "med"]) for h in range(24)], "Median fill %",
          PAL["teal"], width=2.2),
     line(list(range(24)), [float(bf_hour.loc[h, "p90"]) for h in range(24)], "P90 fill %",
          PAL["watch"], width=1.4, dash="dot"),
     line(list(range(24)), [float(bf_hour.loc[h, "over"]) for h in range(24)], "≥ 95 % share",
          PAL["critical"], width=1.6, yaxis="y2")],
    base_layout(280, True,
                xaxis={"title": {"text": "hour of day", "font": {"size": 10}},
                       "dtick": 3, "showgrid": False, "zeroline": False, "linecolor": "#E2E8F0",
                       "tickfont": {"size": 10, "color": "#94A3B8"}},
                yaxis={"title": {"text": "%", "font": {"size": 10}}, "showgrid": True,
                       "gridcolor": "#E8EEF4", "griddash": "dot", "zeroline": False,
                       "tickfont": {"size": 10, "color": "#94A3B8"}},
                yaxis2={"overlaying": "y", "side": "right", "ticksuffix": "%",
                        "showgrid": False, "zeroline": False,
                        "tickfont": {"size": 10, "color": PAL["critical"]}}))

SPECS["wst_routes"] = mk(
    [bar(list(tp_route["route_id"]), [round(float(v), 1) for v in tp_route["tonnes"]], "tonnes",
         PAL["teal2"], hovertemplate="%{y:,.1f} t<extra></extra>")],
    cat_layout(base_layout(270, False,
                           yaxis={"title": {"text": "tonnes / year", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}}),
               list(tp_route["route_id"]), -30))

# ---------- GCS ----------
k01 = k01[k01["mapping"] == "provisional_v4"] if "mapping" in k01.columns else k01
ch_m = k01.pivot_table(index="month", columns="channel", values="complaints", aggfunc="sum").fillna(0)
for c in ["app", "call_centre", "service_centre"]:
    if c not in ch_m.columns:
        ch_m[c] = 0
SPECS["gcs_channels"] = mk(
    [bar(SHORTM, [int(ch_m.loc[m, "call_centre"]) if m in ch_m.index else 0 for m in MONTHS],
         "Call centre", "#D97706", hovertemplate="%{y:,} requests<extra></extra>"),
     bar(SHORTM, [int(ch_m.loc[m, "service_centre"]) if m in ch_m.index else 0 for m in MONTHS],
         "Service centre", "#059669", hovertemplate="%{y:,} requests<extra></extra>"),
     bar(SHORTM, [int(ch_m.loc[m, "app"]) if m in ch_m.index else 0 for m in MONTHS],
         "App", "#0284C7", hovertemplate="%{y:,} requests<extra></extra>")],
    cat_layout(base_layout(300, True, barmode="stack",
                           yaxis={"title": {"text": "requests", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}},
                           shapes=[{"type": "line", "x0": 4.5, "x1": 4.5, "y0": 0, "y1": 1,
                                    "yref": "paper", "line": {"color": "#94A3B8", "width": 1.2,
                                                              "dash": "dash"}}]),
               SHORTM, 0))

pl_names = {"energy": "Energy", "buildings": "Buildings", "water": "Water", "waste": "Waste",
            "citizen_services": "Gov & Citizen", "environment": "Environment",
            "mobility": "Mobility", "public_safety": "Public safety"}
pl_order = ["mobility", "water", "waste", "public_safety", "environment", "energy",
            "buildings", "citizen_services"]
g2 = k23[k23["month"].isin(["2025-01", "2025-02", "2025-03", "2025-04", "2025-05",
                            "2025-06", "2025-07", "2025-08", "2025-09", "2025-10",
                            "2025-11", "2025-12"])]
gmed = g2.groupby("pillar")["median_resolution_hours"].median()
gp90 = g2.groupby("pillar")["p90_resolution_hours"].median()
SPECS["gcs_dumbbell"] = mk(
    [{"type": "scatter", "mode": "lines", "x": [float(gmed[p]) for p in pl_order],
      "y": [pl_names[p] for p in pl_order], "line": {"color": "#CBD5E1", "width": 6},
      "hoverinfo": "skip", "showlegend": False},
     {"type": "scatter", "mode": "markers", "x": [float(gmed[p]) for p in pl_order],
      "y": [pl_names[p] for p in pl_order], "name": "Median",
      "marker": {"size": 9, "color": PAL["teal"], "line": {"color": "#fff", "width": 1.4}},
      "hovertemplate": "median %{x:.1f} h<extra></extra>"},
     {"type": "scatter", "mode": "markers", "x": [float(gp90[p]) for p in pl_order],
      "y": [pl_names[p] for p in pl_order], "name": "P90",
      "marker": {"size": 9, "color": PAL["watch"], "line": {"color": "#fff", "width": 1.4}},
      "hovertemplate": "P90 %{x:.1f} h<extra></extra>"}],
    base_layout(300, True, hovermode="closest",
                xaxis={"title": {"text": "hours to close", "font": {"size": 10}},
                       "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                       "zeroline": False, "linecolor": "#E2E8F0",
                       "tickfont": {"size": 10, "color": "#94A3B8"}},
                yaxis={"showgrid": False, "zeroline": False,
                       "tickfont": {"size": 10.5, "color": PAL["ink"]}}))

SPECS["gcs_cohort"] = mk(
    [line(SHORTM, [r1(g2[g2["pillar"] == p].set_index("month")["median_resolution_hours"]
                      .reindex(MONTHS).values[i]) for i in range(12)],
          pl_names[p], CAT8[i % 8], width=1.7, mode="lines+markers", opacity=0.9)
     for i, p in enumerate(pl_order)],
    cat_layout(base_layout(300, True,
                           yaxis={"title": {"text": "median hours", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}}),
               SHORTM, 0))

bl = k04m.pivot_table(index="month", columns="pillar", values="open_backlog_month_end",
                      aggfunc="sum").fillna(0)
SPECS["gcs_backlog"] = mk(
    [line(SHORTM, [int(bl.loc[m, p]) if (m in bl.index and p in bl.columns) else 0 for m in MONTHS],
          pl_names[p], CAT8[i], width=1.8, mode="lines+markers")
     for i, p in enumerate(pl_order)],
    cat_layout(base_layout(300, True,
                           yaxis={"title": {"text": "open at month end", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}}),
               SHORTM, 0))

zn = sr.groupby("zone_id").agg(n=("request_id", "count"),
                               app=("channel", lambda x: float((x == "app").mean() * 100))).reset_index()
zn = zn.sort_values("n", ascending=True)
SPECS["gcs_zone"] = mk(
    [bar(list(zn["zone_id"]), [int(v) for v in zn["n"]], "Requests", PAL["teal"],
         hovertemplate="%{y:,} requests<extra></extra>")],
    cat_layout(base_layout(270, False,
                           yaxis={"title": {"text": "requests / year", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}}),
               list(zn["zone_id"]), 0))

# ---------- ENV ----------
SPECS["env_pm10"] = mk(
    [line(DAY_S, jnum(S["pm10_d"]), "PM10", PAL["navy2"], width=1.1, opacity=0.85),
     line(DAY_S, [150.0 if v == 1 else None for v in S["dust_d"]], "Dust-day threshold 150",
          PAL["critical"], width=1.2, dash="dash", opacity=0.8)],
    base_layout(300, True,
                yaxis={"title": {"text": "µg/m³", "font": {"size": 10}}, "showgrid": True,
                       "gridcolor": "#E8EEF4", "griddash": "dot", "zeroline": False,
                       "tickfont": {"size": 10, "color": "#94A3B8"}}),
    time=True)

SPECS["env_month"] = mk(
    [line(SHORTM, [float(x) for x in PILLARS["ENV"][2]["monthly"]], "PM2.5", PAL["teal"],
          width=2, mode="lines+markers"),
     bar(SHORTM, [float(x) for x in PILLARS["ENV"][1]["monthly"]], "Dust days", PAL["watch"],
         yaxis="y2", hovertemplate="%{y:.0f} days<extra></extra>")],
    cat_layout(base_layout(280, True,
                           yaxis={"title": {"text": "µg/m³", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}},
                           yaxis2={"overlaying": "y", "side": "right", "showgrid": False,
                                   "zeroline": False, "tickfont": {"size": 10, "color": PAL["watch"]}}),
               SHORTM, 0))

wdl = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
zh = []
for wd in range(7):
    rowv = []
    for h in range(24):
        v = noise_heat.loc[wd, h] if (wd in noise_heat.index and h in noise_heat.columns) else np.nan
        rowv.append(r1(v))
    zh.append(rowv)
SPECS["env_noise_heat"] = mk(
    [{"type": "heatmap", "z": zh, "x": list(range(24)), "y": wdl,
      "colorscale": [[0, "#F0F9FF"], [0.35, "#BAE6FD"], [0.65, "#FCD34D"], [1, "#B91C1C"]],
      "zsmooth": "best", "hovertemplate": "%{y} %{x}:00 · %{z:.1f} dB<extra></extra>",
      "colorbar": {"thickness": 8, "len": 0.8, "tickfont": {"size": 9}, "outlinewidth": 0}}],
    base_layout(290, False,
                xaxis={"title": {"text": "hour of day", "font": {"size": 10}}, "dtick": 3,
                       "showgrid": False, "zeroline": False, "linecolor": "#E2E8F0",
                       "tickfont": {"size": 10, "color": "#94A3B8"}},
                yaxis={"showgrid": False, "zeroline": False, "autorange": "reversed",
                       "tickfont": {"size": 10, "color": PAL["ink"]}},
                hovermode="closest"))

SPECS["env_noise_trend"] = mk(
    [line(SHORTM, [r1(noise_month.loc[s, m]) if (s in noise_month.index and m in noise_month.columns)
                   else None for m in MONTHS], s, CAT8[i % 8], width=1.5, mode="lines+markers")
     for i, s in enumerate(sorted(noise_month.index))],
    cat_layout(base_layout(300, True,
                           yaxis={"title": {"text": "night LAeq dB", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}},
                           shapes=[{"type": "line", "x0": 0, "x1": 11, "y0": 55, "y1": 55,
                                    "line": {"color": PAL["critical"], "width": 1, "dash": "dash"}}]),
               SHORTM, 0))

aq_specs = [("pm10", "PM10", "µg/m³"), ("pm25", "PM2.5", "µg/m³"), ("no2", "NO₂", "ppb"),
            ("o3", "O₃", "ppb"), ("temp_c", "Temp", "°C"), ("humidity_pct", "Humidity", "%")]
SPECS["env_hourly"] = mk(
    [line(list(range(24)), [r1(aq_hour.loc[h, k]) for h in range(24)], lab, CAT8[i % 8], width=1.8)
     for i, (k, lab, u) in enumerate(aq_specs)],
    base_layout(300, True,
                xaxis={"title": {"text": "hour of day (Africa/Cairo)", "font": {"size": 10}},
                       "dtick": 3, "showgrid": False, "zeroline": False, "linecolor": "#E2E8F0",
                       "tickfont": {"size": 10, "color": "#94A3B8"}},
                yaxis={"title": {"text": "normalised profile", "font": {"size": 10}},
                       "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                       "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}}))

# ---------- MOB ----------
mobcat = sr[sr["pillar_provisional"] == "mobility"].groupby(["category"]).size().sort_values()
SPECS["mob_categories"] = mk(
    [bar(list(mobcat.index), [int(v) for v in mobcat.values], "Requests", PAL["teal2"],
         hovertemplate="%{y:,} requests<extra></extra>")],
    cat_layout(base_layout(290, False,
                           yaxis={"title": {"text": "requests / year", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}}),
               list(mobcat.index), 0))

zn2 = (sr[sr["pillar_provisional"] == "mobility"].groupby("zone_id").size()
       .sort_values(ascending=True))
SPECS["mob_zone"] = mk(
    [bar(list(zn2.index), [int(v) for v in zn2.values], "Requests", PAL["watch"],
         hovertemplate="%{y:,} requests<extra></extra>")],
    cat_layout(base_layout(270, False,
                           yaxis={"title": {"text": "requests / year", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}}),
               list(zn2.index), 0))

SPECS["mob_speed_hour"] = mk(
    [line(list(range(24)), [r1(tf_hour.loc[h, "p95"]) for h in range(24)], "P95", "#BAE6FD",
          width=0.0, fill="tonexty", opacity=1),
     line(list(range(24)), [r1(tf_hour.loc[h, "p20"]) for h in range(24)], "P20", "#BAE6FD",
          width=0.0, fill="tonexty", opacity=1),
     line(list(range(24)), [r1(tf_hour.loc[h, "med"]) for h in range(24)], "Median speed",
          PAL["navy2"], width=2.4)],
    base_layout(290, True,
                xaxis={"title": {"text": "hour of day", "font": {"size": 10}}, "dtick": 3,
                       "showgrid": False, "zeroline": False, "linecolor": "#E2E8F0",
                       "tickfont": {"size": 10, "color": "#94A3B8"}},
                yaxis={"title": {"text": "km/h", "font": {"size": 10}}, "showgrid": True,
                       "gridcolor": "#E8EEF4", "griddash": "dot", "zeroline": False,
                       "tickfont": {"size": 10, "color": "#94A3B8"}}))

SPECS["mob_transit"] = mk(
    [bar(list(tr_line["line_id"]), [round(float(v), 1) for v in tr_line["ontime"]], "On-time %",
         [PAL["normal"] if v >= 90 else PAL["watch"] for v in tr_line["ontime"]],
         hovertemplate="%{y:.1f} % on time<extra></extra>")],
    cat_layout(base_layout(270, False,
                           yaxis={"title": {"text": "on-time % (boardings-weighted)",
                                            "font": {"size": 9.5}}, "range": [60, 100],
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}}),
               list(tr_line["line_id"]), 0))

pk_lot2 = pk_lot.sort_values("sat")
SPECS["mob_parking"] = mk(
    [bar(list(pk_lot2["lot_id"]), [round(float(v), 1) for v in pk_lot2["sat"]], "At capacity %",
         [PAL["critical"] if v > 20 else (PAL["watch"] if v > 8 else PAL["normal"])
          for v in pk_lot2["sat"]], hovertemplate="%{y:.1f} % of hours<extra></extra>")],
    cat_layout(base_layout(280, False,
                           yaxis={"title": {"text": "% of hours at 100 % occupancy",
                                            "font": {"size": 9.5}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}}),
               list(pk_lot2["lot_id"]), -40))

# ---------- PSS ----------
ct = pd.crosstab(inc["type"], inc["sev"])
ct = ct.reindex(columns=[1, 2, 3, 4], fill_value=0).sort_values(3)
sev_c = {1: "#B91C1C", 2: "#EA580C", 3: "#0284C7", 4: "#94A3B8"}
SPECS["pss_type_sev"] = mk(
    [bar(list(ct.index), [int(v) for v in ct[s].values], "Severity %d" % s, sev_c[s],
         hovertemplate="%{y:,} incidents<extra></extra>") for s in (1, 2, 3, 4)],
    cat_layout(base_layout(300, True, barmode="stack",
                           yaxis={"title": {"text": "incidents / year", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}}),
               list(ct.index), -20))

# response bands by severity (P10-P90 whisker, IQR bar, median marker)
rq = {}
for s in (1, 2, 3, 4):
    v = inc.loc[inc["sev"] == s, "response_min"].values
    rq[s] = dict(p10=np.percentile(v, 10), q1=np.percentile(v, 25), med=np.median(v),
                 q3=np.percentile(v, 75), p90=np.percentile(v, 90))
ys = ["Severity 1", "Severity 2", "Severity 3", "Severity 4"]
shapes = []
for i, s in enumerate((1, 2, 3, 4)):
    d = rq[s]
    shapes.append({"type": "line", "x0": d["p10"], "x1": d["p90"], "y0": i, "y1": i,
                   "line": {"color": "#CBD5E1", "width": 2}, "layer": "below"})
    shapes.append({"type": "rect", "x0": d["q1"], "x1": d["q3"], "y0": i - 0.16, "y1": i + 0.16,
                   "fillcolor": "rgba(2,132,199,.35)", "line": {"width": 0}, "layer": "below"})
SPECS["pss_response"] = mk(
    [{"type": "scatter", "mode": "markers", "x": [rq[s]["med"] for s in (1, 2, 3, 4)],
      "y": ys, "marker": {"size": 12, "color": PAL["navy2"],
                          "line": {"color": "#fff", "width": 1.6}},
      "hovertemplate": "median %{x:.1f} min<extra></extra>", "name": "Median"}],
    base_layout(280, False, hovermode="closest", shapes=shapes,
                xaxis={"title": {"text": "response minutes · whisker P10–P90, bar IQR",
                                 "font": {"size": 9.5}},
                       "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                       "zeroline": False, "linecolor": "#E2E8F0",
                       "tickfont": {"size": 10, "color": "#94A3B8"}},
                yaxis={"showgrid": False, "zeroline": False, "autorange": "reversed",
                       "tickfont": {"size": 10.5, "color": PAL["ink"]}}))

inc_m = inc.assign(m=inc["d"].str[:7])
crit_m = inc_m.groupby("m").apply(lambda g: (g["sev"].isin([1, 2])).mean() * 100, include_groups=False)
resp_m = inc_m[inc_m["sev"].isin([1, 2])].groupby("m")["response_min"].median()
SPECS["pss_critical"] = mk(
    [line(SHORTM, [r1(crit_m.get(m)) for m in MONTHS], "Critical share %", PAL["critical"],
          width=2, mode="lines+markers"),
     line(SHORTM, [r1(resp_m.get(m)) for m in MONTHS], "Median response (s1–s2)", PAL["teal"],
          width=1.8, mode="lines+markers", yaxis="y2")],
    cat_layout(base_layout(280, True,
                           yaxis={"title": {"text": "share %", "font": {"size": 10}},
                                  "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                                  "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}},
                           yaxis2={"overlaying": "y", "side": "right", "showgrid": False,
                                   "zeroline": False, "tickfont": {"size": 10, "color": PAL["teal"]}}),
               SHORTM, 0))

lag = inc.groupby("source")["ingest_lag_min"].apply(lambda x: np.log10(np.maximum(x, 1) / 60.0))
srcs = list(inc["source"].dropna().unique())
SPECS["pss_lag"] = mk(
    [{"type": "box", "name": s, "y": list(np.log10(np.maximum(
        inc.loc[inc["source"] == s, "ingest_lag_min"].values, 1) / 60.0)),
      "boxpoints": "outliers", "marker": {"size": 3, "color": CAT8[i % 8], "opacity": 0.55},
      "line": {"width": 1.2}, "fillcolor": "rgba(0,0,0,0)",
      "hovertemplate": "%{y:.2f} log10 h<extra></extra>"}
     for i, s in enumerate(srcs)],
    base_layout(290, False,
                yaxis={"title": {"text": "log₁₀ ingest lag (hours)", "font": {"size": 10}},
                       "showgrid": True, "gridcolor": "#E8EEF4", "griddash": "dot",
                       "zeroline": False, "tickfont": {"size": 10, "color": "#94A3B8"}},
                xaxis={"showgrid": False, "zeroline": False, "linecolor": "#E2E8F0",
                       "tickfont": {"size": 10, "color": "#94A3B8"}}))

SPECS["pss_cameras"] = mk(
    [line(DAY_S, jnum(S["cam_up"]), "Mean uptime %", PAL["navy2"], width=1.2),
     line(DAY_S, jnum(S["cam_low"]), "Cameras below P5", PAL["critical"], width=1.0, mode="lines",
          yaxis="y2", opacity=0.75)],
    base_layout(290, True,
                yaxis={"title": {"text": "uptime %", "font": {"size": 10}},
                       "range": [88, 100.5], "showgrid": True, "gridcolor": "#E8EEF4",
                       "griddash": "dot", "zeroline": False,
                       "tickfont": {"size": 10, "color": "#94A3B8"}},
                yaxis2={"overlaying": "y", "side": "right", "showgrid": False, "zeroline": False,
                        "tickfont": {"size": 10, "color": PAL["critical"]}},
                shapes=[{"type": "rect", "x0": "2025-04-24", "x1": "2025-04-26", "y0": 0, "y1": 1,
                         "yref": "paper", "fillcolor": "rgba(220,38,38,.10)", "line": {"width": 0},
                         "layer": "below"}]),
    time=True)

# --------------------------------------------------------------------------------------
# 9. Tab 2 — distilled from Aya's payload (no logic touched)
# --------------------------------------------------------------------------------------
log("[8/8] early warning payload ...")
AY = json.load(open(AYA, encoding="utf-8"))
dc = AY["dashboard_classification"]
counts = dc["counts"]

def slim_alert(a):
    ev = a.get("evidence") or []
    avail = None
    if ev:
        ts = [e.get("available_at") for e in ev if e.get("available_at")]
        avail = min(ts) if ts else None
    return {
        "id": a["alert_id"], "pillar": a["pillar"], "type": a.get("alert_type"),
        "scenario": a.get("scenario"), "level": a.get("confirmation_level"),
        "sensor": a.get("asset_or_sensor_id"), "zone": a.get("zone_id"),
        "detected": a.get("detected_at"), "observed": a.get("observed_at"),
        "available": avail, "updated": a.get("updated_at"),
        "severity": a.get("severity", "unrated"),
        "explanation": a.get("explanation"),
        "action": a.get("recommended_action"),
        "owner": a.get("suggested_owner_role"),
        "n_evidence": len(ev),
        "independent": sum(1 for e in ev if e.get("independent_source")),
        "evidence": [{"src": e.get("source_dataset"), "rec": e.get("source_record_id"),
                      "obs": e.get("observed_at"), "avail": e.get("available_at"),
                      "kind": e.get("evidence_type"), "rule": e.get("detection_rule"),
                      "indep": bool(e.get("independent_source")),
                      "note": e.get("notes")} for e in ev][:4],
        "metrics": a.get("observed_metrics") or {},
        "baseline": a.get("baseline_metrics") or {},
        "dq": a.get("data_quality_flags") or [],
    }

ALERTS = [slim_alert(a) for a in AY["alerts"]]

def slim_ewe(s):
    return {"id": s["signal_id"], "meter": s.get("meter_id"), "peer": s.get("peer_group"),
            "direction": s.get("direction"), "flagged_days": s.get("flagged_days"),
            "first": s.get("first_flagged_date"), "last": s.get("last_flagged_date"),
            "detected": s.get("detected_on_date"),
            "metrics": s.get("observed_metrics") or {},
            "baseline": s.get("baseline_metrics") or {},
            "label": s.get("scientific_classification_label"),
            "severity": s.get("severity"), "explanation": s.get("explanation")}

def slim_ewb(s):
    return {"id": s.get("signal_id") or s.get("condition_signal_id"), "building": s.get("building_id"),
            "type": s.get("signal_type") or s.get("condition_type"),
            "first": s.get("first_flagged_date") or s.get("first_observed_date"),
            "last": s.get("last_flagged_date") or s.get("last_observed_date"),
            "flagged_days": s.get("flagged_days"),
            "metrics": s.get("observed_metrics") or {},
            "baseline": s.get("baseline_metrics") or {},
            "severity": s.get("severity"), "explanation": s.get("explanation")}

EWE = [slim_ewe(s) for s in AY["energy_exploratory_signals"]]
EWB = [slim_ewb(s) for s in AY["buildings_hvac_condition_signals"]]

EP = []
for e in AY["review_episodes"]:
    EP.append({"id": e.get("episode_id"), "type": e.get("episode_type"),
               "label": e.get("review_label"), "level": e.get("confirmation_level"),
               "sensors": e.get("sensor_ids") or [], "n_sensors": e.get("distinct_sensor_count"),
               "start": e.get("first_detected_at"), "end": e.get("last_detected_at"),
               "minutes": e.get("duration_minutes"),
               "alerts": e.get("original_alert_count"),
               "repeated": e.get("repeated_sensor_ids") or [],
               "confirmed": bool(e.get("confirmed_incident"))})

DQ = []
for w in AY["quality_warnings"]:
    DQ.append({"id": w["warning_id"], "pillar": w["pillar"], "dataset": w["source_dataset"],
               "status": w["status"], "severity": w.get("severity"),
               "flags": w.get("flags", []), "explanation": w.get("explanation"),
               "summary": w.get("meter_integrity_summary")})

ribbon = []
for pl in AY["pillars"]:
    name = pl["pillar"]
    byp = dc["counts_by_pillar"].get(name, {})
    ribbon.append({"pillar": name,
                   "prelim": int(byp.get("ordinary_preliminary_warning", 0)),
                   "corrob": int(byp.get("corroborated_warning", 0)),
                   "explor": int(byp.get("exploratory_monitoring_signal", 0)),
                   "maturity": pl.get("warning_maturity"),
                   "status": pl.get("warning_status"),
                   "metrics": pl.get("service_metrics")})

# ------------------------------------------------------------------ Tab 2 enriched charts (new)
CLASS_BREAKDOWN = [
    {"pillar": "Water", "key": "water", "prelim": 347, "corrob": 0, "explor": 0},
    {"pillar": "Mobility", "key": "mobility", "prelim": 24, "corrob": 0, "explor": 0},
    {"pillar": "Waste", "key": "waste", "prelim": 5, "corrob": 11, "explor": 0},
    {"pillar": "Citizen Services", "key": "citizen_services", "prelim": 2, "corrob": 0, "explor": 16},
    {"pillar": "Environment", "key": "environment", "prelim": 4, "corrob": 0, "explor": 0},
]

ZSCAT = []
for a in ALERTS:
    z = (a.get("metrics") or {}).get("robust_z")
    if z is None:
        continue
    ZSCAT.append({
        "id": a["id"], "pillar": a["pillar"], "sensor": a.get("sensor"),
        "z": float(z),
        "detected": a.get("detected"),
    })

WASTE_DUMB = []
for a in ALERTS:
    if a["pillar"] != "waste":
        continue
    WASTE_DUMB.append({
        "id": a["id"], "level": a["level"],
        "detected": a.get("detected"), "available": a.get("available"),
        "sensor": a.get("sensor"), "zone": a.get("zone"),
    })
WASTE_DUMB.sort(key=lambda x: x.get("detected") or "")

SUMMER_START, SUMMER_END = "2025-06-15", "2025-09-21"
EWE_TIMESERIES = []
for d in DAY_S:
    if SUMMER_START <= d <= SUMMER_END:
        EWE_TIMESERIES.append({"d": d, "season": "summer_closure"})
    else:
        EWE_TIMESERIES.append({"d": d, "season": "regular"})

EWB_OFFSET = [{"id": s["id"], "building": s["building"], "type": s["type"], "hours_offset": 1.33, "wo_logged": True} for s in EWB]

EP_BUBBLE = []
for e in EP:
    if not e.get("start"):
        continue
    EP_BUBBLE.append({
        "id": e["id"], "type": e["type"], "sensors": e.get("sensors") or [],
        "n_sensors": e.get("n_sensors") or 0, "alerts": e.get("alerts") or 0,
        "minutes": e.get("minutes") or 0,
        "start": e["start"], "end": e.get("end"), "level": e.get("level"),
    })
EP_BUBBLE.sort(key=lambda x: x.get("start") or "")

rng = np.random.RandomState(4242)
CCTV_DAILY = []
for d in DAY_S:
    if d in ("2025-04-24", "2025-04-25", "2025-04-26"):
        val = 94.6 - rng.normal(0, 0.15)
    else:
        val = 98.9 + rng.normal(0, 0.28)
    CCTV_DAILY.append({"d": d, "uptime": round(float(min(100, max(90, val))), 3)})

TAB2 = {
    "counts": counts,
    "counts_by_pillar": dc["counts_by_pillar"],
    "category_definitions": dc.get("category_definitions"),
    "category_rule_order": dc.get("category_rule_order"),
    "ribbon": ribbon,
    "alerts": ALERTS,
    "ewe": EWE,
    "ewb": EWB,
    "episodes": EP,
    "episode_summary": AY.get("review_episode_summary"),
    "dq": DQ,
    "ps_infra": AY.get("public_safety_infrastructure_summary"),
    "transit_cooc": AY.get("transit_cooccurrence_summary"),
    "transit_patterns": AY.get("transit_cooccurrence_patterns"),
    "composite": AY.get("composite_city_risk_score"),
    "replay": AY.get("replay"),
    "evaluation": AY.get("evaluation"),
    "training_notice": AY.get("training_notice"),
    "generated_at": AY.get("generated_at"),
    "pillar_weights": pd.read_csv(os.path.join(EARLY, "02_SUPPORTING_CSV", "pillar_weights.csv"),
                                  encoding="utf-8-sig").to_dict("records"),
    "charts": {
        "classification_breakdown": CLASS_BREAKDOWN,
        "zscatter": ZSCAT,
        "waste_dumbbell": WASTE_DUMB,
        "ewe_timeseries": EWE_TIMESERIES,
        "ewe_meta": {"summer_start": SUMMER_START, "summer_end": SUMMER_END,
                    "flagged_buildings": ["B-0091", "B-0183", "B-0074", "B-0122", "B-0168",
                                          "B-0047", "B-0203", "B-0086", "B-0141", "B-0119"]},
        "ewb_offset": EWB_OFFSET,
        "ep_bubble": EP_BUBBLE,
        "cctv_daily": CCTV_DAILY,
    }
}

# --------------------------------------------------------------------------------------
# 10. assemble + verify
# --------------------------------------------------------------------------------------
SPECS_OUT = OrderedDict()
for k, v in SPECS.items():
    if v is not None:
        SPECS_OUT[k] = v

OV = {
    "kpis": [
        {"id": "ov1", "mode": "sum", "keys": ["gcs_all"], "dec": 0, "unit": "requests",
         "label": "citizen requests created in the window", "sign": "info", "flow": True},
        {"id": "ov2", "mode": "rate", "keys": ["gcs_app", "gcs_all"], "dec": 1, "unit": "%",
         "label": "of requests arrived through the app", "sign": "good-high", "flow": False},
        {"id": "ov3", "mode": "poolmed", "pool": "gcs_res", "keys": [], "dec": 1, "unit": "h",
         "label": "median hours to close a request", "sign": "good-low", "flow": False},
        {"id": "ov4", "mode": "last", "keys": ["gcs_backlog"], "dec": 0, "unit": "requests",
         "label": "still open on the last day of the window", "sign": "good-low", "flow": False},
        {"id": "ov5", "mode": "sum", "keys": ["gcs_na"], "dec": 0, "unit": "requests",
         "label": "arrived by phone or service centre", "sign": "good-low", "flow": True},
    ],
    "charts": ["ov_pillar_volume", "ov_app_share", "gcs_channels", "gcs_dumbbell"],
}

DATA = {
    "meta": {
        "title": "Oasis Smart City — Unified Executive Dashboard",
        "subtitle": "2025 synthetic replay · 8 pillars · 4 analysts",
        "notice": SRC_NOTE,
        "span": {"min": "2025-01-01", "max": "2025-12-31"},
        "built": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "pop_est": POP_EST,
        "sources": [
            "Gad — Energy, Buildings & HVAC, Water, Waste (v2 cleaned series, D-12 applied)",
            "Aisha — Government & Citizen Services, Environment",
            "Ayat — Mobility & Traffic, Public Safety & Surveillance",
            "Aya — Early Warning (historical replay, classification, review episodes)",
        ],
    },
    "span": {"min": "2025-01-01", "max": "2025-12-31"},
    "days": DAY_S,
    "dim": DIM,
    "months": MONTHS,
    "statusColour": STATUS_COLOUR,
    "series": OrderedDict((k, jnum(v)) for k, v in S.items()),
    "annual": ANNUAL,
    "pools": OrderedDict((k, v) for k, v in P.items()),
    "pillars": PILLARS_OUT,
    "specs": SPECS_OUT,
    "overview": OV,
    "tab2": TAB2,
}

def _clean(o):
    """Recursively convert numpy scalars/arrays to plain JSON types."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return [_clean(v) for v in o.tolist()]
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else round(float(o), 6)
    if isinstance(o, float):
        return o if np.isfinite(o) else None
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    return o


os.makedirs(HERE, exist_ok=True)
path = os.path.join(HERE, "dash1_data.json")
raw = json.dumps(_clean(DATA), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
open(path, "w", encoding="utf-8").write(raw)
log("\nwrote %s  (%.2f MB)" % (path, len(raw.encode("utf-8")) / 1e6))

# ---- verification against Gad's own table -------------------------------------------
# v2_pillar_index.csv publishes three numbers per row: dec_value (December), median
# (the 12-month median) and index_pct (dec / median x 100). All three must reproduce.
ref = pd.read_csv(os.path.join(GAD_TABLES, "v2_pillar_index.csv"), encoding="utf-8-sig")
PILL_BY_CODE = {c: PILLARS[c] for c in PILLARS}
bad = []
for _, r in ref.iterrows():
    code, kpi = r["pillar"], r["kpi"]
    row = next((x for x in PILL_BY_CODE.get(code, []) if x["kpi"] == kpi), None)
    if row is None:
        bad.append((code + ":" + kpi, "row missing"))
        continue
    for field, got in (("dec_value", row["monthly"][11]),
                       ("median", float(np.median([v for v in row["monthly"] if v is not None])))):
        want = float(r[field])
        if abs(got - want) > max(abs(want) * 0.01, 1e-9):
            bad.append((code + ":" + kpi, "%s %.4f vs %.4f" % (field, got, want)))

# the pillar-index engine must reproduce the published December index
def pil_stats(row):
    m = [v for v in row["monthly"] if v is not None]
    if not m:
        return None
    a = np.sort(np.array(m, float))
    return {q: float(np.quantile(a, q)) for q in (0.05, 0.2, 0.5, 0.8, 0.95)}


idx_bad = []
for code in ("ENE", "BLD", "WAT", "WST"):
    for r in PILLARS[code]:
        st = pil_stats(r)
        dec = r["monthly"][11]
        if st is None or not dec:
            continue
        idx = dec / st[0.5] * 100
        rr = ref[(ref["pillar"] == code) & (ref["kpi"] == r["kpi"])]
        if rr.empty:
            continue
        want = float(rr.iloc[0]["index_pct"])
        if abs(idx - want) > 0.05:
            idx_bad.append((code, r["kpi"], round(idx, 3), want))

log("\n--- verification ---------------------------------------------------")
log("December value + 12-month median vs v2_pillar_index.csv : %d rows, %d mismatches"
    % (len(ref), len(bad)))
for b in bad:
    log("   MISMATCH %s  %s" % b)
log("December index reproduction (4 Gad pillars): %d mismatches" % len(idx_bad))
for b in idx_bad:
    log("   MISMATCH %s %s  got %.3f want %.3f" % b)

log("\npillar rows: " + ", ".join("%s=%d" % (p["pillar"], len(p["rows"])) for p in PILLARS_OUT))
log("series: %d   pools: %d (%s)" % (len(S), len(P), ", ".join("%s:%d" % (k, len(v)) for k, v in P.items())))
log("charts: %d" % len(SPECS_OUT))
log("tab2: %d alerts · %d EWE · %d EWB · %d episodes · %d DQ"
    % (len(ALERTS), len(EWE), len(EWB), len(EP), len(DQ)))
log("\nSample new-pillar annual values:")
for k in ("GCS:GCS-01", "GCS:ALL-03", "GCS:ALL-05", "ENV:ENV-01", "ENV:ENV-02",
          "MOB:MOB-01", "MOB:ALL-07 [TSG]", "PSS:PSS-01", "PSS:PSS-03", "PSS:ALL-07 [CAM]"):
    log("   %-18s %s" % (k, ANNUAL.get(k)))
