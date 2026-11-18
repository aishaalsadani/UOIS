"""Decision Lab API tests (Ayat's 60-day simulator behind citizen_app.py).

Run from the project folder (TheProject\\TheProject):
    .venv\\Scripts\\python.exe -m pytest tests -q

They use a small Flask app with the same simulator routes citizen_app.py registers, so no server and no BERT are needed.
The first run computes the default leaderboard once (cached in cache\\ afterwards).
"""
import csv
import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import simulator_service as S  # noqa: E402

SIM = S.SIM_DIR
pytestmark = pytest.mark.skipif(not S.available(), reason=f"simulator not loaded: {S._state['error']}")


@pytest.fixture(scope="module")
def client():
    from flask import Flask
    app = Flask("simulator_test")
    S.register_flask_routes(app)
    return app.test_client()


def post(client, path, body):
    r = client.post(path, data=json.dumps(body), content_type="application/json")
    return r.status_code, r.get_json()


FIX = {"zone": "Z01", "days": 60, "view": "daily", "scenario": "fix", "category": "streetlights",
       "start_date": "2026-01-15", "reduce_pct": 30}


# ------------------------------------------------------------------ POST /api/simulate: valid
def test_fix_example_reproduced_through_the_api(client):
    """'Fix: Z01 streetlights -30% from 2026-01-15' in outputs/scenario_examples_60d.csv, through POST /api/simulate."""
    status, body = post(client, "/api/simulate", FIX)
    assert status == 200 and body["ok"]
    rows = [r for r in csv.DictReader((SIM / "outputs" / "scenario_examples_60d.csv").open(encoding="utf-8"))
            if r["example"].startswith("Fix: Z01 streetlights")]
    assert len(rows) == 15
    got = {r["category_id"]: r for r in body["by_type"]}
    for r in rows:
        g = got[r["category_id"]]
        for col in ("normal_mean", "normal_p10", "normal_p90", "mean", "p10", "p90", "change", "change_pct"):
            assert abs(float(r[col]) - g[col]) < 1e-9, (r["category_id"], col, r[col], g[col])


@pytest.mark.parametrize("req", [
    {"zone": "Z01", "days": 60, "view": "weekly", "scenario": "fix", "category": "streetlights", "start_date": "2026-01-01", "reduce_pct": 30},
    {"zone": "Z04", "days": 30, "view": "monthly", "scenario": "population", "new_population": 9000},
    {"zone": "Z02", "days": 60, "view": "weekly", "scenario": "ramadan_off"},
    {"zone": "Z06", "days": 17, "view": "daily", "scenario": "normal"},
])
def test_fast_path_equals_original_simulate(client, req):
    """The page uses the fast path; it must give exactly the numbers of Ayat's simulate()."""
    s1, fast = post(client, "/api/simulate", dict(req, include_detail=True))
    s2, ref = post(client, "/api/simulate", dict(req, include_detail=True, engine="reference"))
    assert s1 == s2 == 200
    for k in ("by_type", "by_period", "detail", "total", "assumptions", "dates", "period_dates"):
        assert fast[k] == ref[k], k


def test_response_shape_and_no_nan(client):
    status, body = post(client, "/api/simulate", {"zone": "ALL", "days": 30, "view": "weekly", "scenario": "normal"})
    assert status == 200
    for k in ("by_type", "by_period", "by_zone", "total", "assumptions", "period_dates", "latency_ms"):
        assert k in body
    assert "detail" not in body                       # only with include_detail
    assert len(body["by_period"]) == len(body["period_dates"]) == 5
    pdx = body["period_dates"]
    assert pdx[0] == {"period": "week 1", "start": body["dates"][0], "end": "2026-01-07"}
    assert pdx[1]["start"] == "2026-01-08" and pdx[-1]["end"] == body["dates"][1]
    assert body["by_type"][0]["change_pct"] is None or isinstance(body["by_type"][0]["change_pct"], float)


def test_options_and_cors(client):
    r = client.options("/api/simulate")
    assert r.status_code == 204 and r.headers["Access-Control-Allow-Origin"] == "*"


# ------------------------------------------------------------------ POST /api/simulate: invalid
@pytest.mark.parametrize("bad, words", [
    ({"zone": "Z09"}, "zone must be"),
    ({"zone": "Z01", "days": 61}, "days must be"),
    ({"zone": "Z01", "days": "60"}, "days must be"),
    ({"zone": "Z01", "view": "yearly"}, "view must be"),
    ({"zone": "Z01", "scenario": "magic"}, "scenario must be"),
    (dict(FIX, category="unicorns"), "category must be"),
    (dict(FIX, reduce_pct=150), "reduce_pct must be"),
    (dict(FIX, start_date="not a date"), "start_date must be"),
    (dict(FIX, zone="ALL"), "fix needs a specific zone"),
    ({"zone": "Z04", "scenario": "population", "new_population": 0}, "new_population must be"),
    ({"zone": "Z01", "colour": "red"}, "unknown field"),
])
def test_invalid_simulate_returns_400(client, bad, words):
    status, body = post(client, "/api/simulate", bad)
    assert status == 400 and body["ok"] is False and words in body["error"], body


def test_bad_json_returns_400(client):
    r = client.post("/api/simulate", data="{not json", content_type="application/json")
    assert r.status_code == 400 and "JSON" in r.get_json()["error"]


# ------------------------------------------------------------------ GET /api/simulate/leaderboard
def _leaderboard(client, days=60, pct=30, timeout=900):
    t0 = time.time()
    while True:
        r = client.get(f"/api/simulate/leaderboard?days={days}&reduce_pct={pct}")
        if r.status_code != 202:
            return r
        assert time.time() - t0 < timeout
        time.sleep(0.5)


def test_leaderboard_valid_and_fast_after_first_call(client):
    first = _leaderboard(client)
    assert first.status_code == 200
    t0 = time.time()
    r = client.get("/api/simulate/leaderboard?days=60&reduce_pct=30")
    seconds = time.time() - t0
    assert r.status_code == 200 and seconds < 3, seconds
    body = r.get_json()
    assert body["runs"] == 90 and len(body["top"]) == 10
    prevented = [row["prevented"] for row in body["top"]]
    assert prevented == sorted(prevented, reverse=True)
    top = body["top"][0]
    for k in ("zone", "category_id", "pillar", "prevented", "prevented_pct", "normal_total", "scenario_total",
              "normal_p10", "normal_p90", "p10", "p90"):
        assert k in top
    # the #1 row is a real simulate() run
    s, one = post(client, "/api/simulate", {"zone": top["zone"], "days": 60, "view": "weekly", "scenario": "fix",
                                            "category": top["category_id"], "start_date": "2026-01-01", "reduce_pct": 30,
                                            "engine": "reference"})
    t = next(x for x in one["by_type"] if x["category_id"] == top["category_id"])
    assert abs((t["normal_mean"] - t["mean"]) - top["prevented"]) < 0.011


@pytest.mark.parametrize("q", ["days=45&reduce_pct=30", "days=60&reduce_pct=25", "days=abc&reduce_pct=30"])
def test_leaderboard_invalid_returns_400(client, q):
    r = client.get("/api/simulate/leaderboard?" + q)
    assert r.status_code == 400 and r.get_json()["ok"] is False


# ------------------------------------------------------------------ meta + frames
def test_meta(client):
    r = client.get("/api/simulate/meta")
    m = r.get_json()
    assert r.status_code == 200 and len(m["zones"]) == 6 and len(m["categories"]) == 15
    assert m["ramadan"]["assumed"] is True
    assert set(m["accuracy_pct"]) == {"daily", "weekly", "monthly"}


def test_frames_last_frame_equals_simulate(client):
    status, f = post(client, "/api/simulate/frames", dict(FIX, view="weekly", steps=4))
    assert status == 200 and len(f["frames"]) == 5 and f["frames"][0]["reduce_pct"] == 0
    s, one = post(client, "/api/simulate", dict(FIX, view="weekly", engine="reference"))
    assert f["frames"][-1]["total"] == one["total"]
    assert f["frames"][0]["total"]["change"] == 0


def test_frames_invalid(client):
    status, body = post(client, "/api/simulate/frames", dict(FIX, steps=99))
    assert status == 400
