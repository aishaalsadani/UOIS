"""Cost of delay engine and API. Runs with pytest, or directly: python tests/test_cost_engine.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cost_engine as E  # noqa: E402
import cost_service as S  # noqa: E402

SUMMARY = E.compute(write=False)


def test_prices_used_are_the_found_ones():
    p = SUMMARY["prices"]
    assert p["electricity_egp_kwh"]["value"] == 2.74 and p["electricity_egp_kwh"]["status"] == "verified"
    assert p["water_price_egp_m3"]["value"] == 4.5 and p["water_price_egp_m3"]["status"] == "provisional"
    assert p["complaint_handling_egp"]["value"] is None  # missing prices stay empty


def test_leak_and_hvac_rates():
    d = SUMMARY["derived"]
    assert abs(d["egp_per_hour"]["Water network"] - d["leak_excess_lps"] * 3.6 * 4.5) < 1e-9
    assert abs(d["egp_per_hour"]["HVAC"] - d["hvac_excess_kw"] * 2.74) < 1e-9
    for c in ("Streetlight", "CCTV", "Traffic signal", "Sensor", "Waste bin"):
        assert d["egp_per_hour"][c] is None  # no price yet -> hours and risk only


def test_scenarios_never_exceed_today():
    a, d = E.load_assumptions(), E.derive_from_warnings()
    closed, _, to_be = E.work_orders(a, d)
    for r in closed:
        assert r["y_stretch"] <= r["y_target"] <= r["x_hours"] + 1e-9
        assert r["y_conservative"] <= min(r["x_hours"], r["sla_hours"]) + 1e-9
    for r in to_be:
        assert r["y_mean_h_stretch"] <= r["y_mean_h_target"] <= r["x_mean_h"]


def test_water_loss_levels():
    w = SUMMARY["water_loss"]
    base, tgt, strc = w["levels"]
    assert (base["nrw"], tgt["nrw"], strc["nrw"]) == (0.249, 0.20, 0.15)
    assert abs(base["lost_m3_year"] - w["billed_m3_year"] * 0.249 / 0.751) < 1e-6
    assert 0 < tgt["saved_m3_year"] < strc["saved_m3_year"]
    assert abs(tgt["saved_egp_year"] - tgt["saved_m3_year"] * 4.5) < 1e-6


def test_risk_index_range():
    assert {r["pillar"] for r in SUMMARY["risk"]} == set(E.PILLARS)
    assert all(0 <= r["risk_index"] <= 100 for r in SUMMARY["risk"])


def test_api_dispatch():
    assert S.dispatch("GET", "/api/other", {}, "") is None
    assert S.dispatch("OPTIONS", "/api/cost/summary", {}, "") == (204, None)
    assert S.dispatch("GET", "/api/cost/recompute", {}, "")[0] == 405
    status, body = S.dispatch("GET", "/api/cost/summary", {}, "")
    assert status == 200 and body["ok"] and body["totals"]["work_orders_used"] > 1000
    status, body = S.dispatch("GET", "/api/cost/live", {}, "")
    assert status == 200 and "running_loss" in body


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
