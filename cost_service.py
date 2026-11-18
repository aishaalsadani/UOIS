"""Cost of Delay API for citizen_app.py (same pattern as simulator_service.py).

Routes (read-only except recompute):
    GET  /api/cost/summary    -> everything the "Cost of delay" tab shows (cost_engine.compute())
    GET  /api/cost/live       -> open work orders at the end of the data + the loss that keeps running
    GET  /api/cost/prices     -> the prices used, with status and source
    POST /api/cost/recompute  -> re-run the engine after editing CostEngine/cost_assumptions.csv

Results are cached in CostEngine/outputs/cost_summary.json and rebuilt when the prices file
or cost_engine.py is newer than the cache.
"""
import json
import os
import threading
import time

import cost_engine as ENGINE

ROUTES = ["/api/cost/summary", "/api/cost/live", "/api/cost/prices", "/api/cost/recompute"]
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Allow-Private-Network": "true"}

_LOCK = threading.Lock()
_STATE = {"summary": None, "error": None, "computing": False, "loaded_at": None}


def _cache_fresh():
    p = ENGINE.SUMMARY_JSON
    if not os.path.exists(p):
        return False
    newest_input = max(os.path.getmtime(ENGINE.ASSUMPTIONS), os.path.getmtime(ENGINE.__file__))
    return os.path.getmtime(p) >= newest_input


def get_summary(force=False):
    with _LOCK:
        if _STATE["summary"] is not None and not force and _cache_fresh():
            return _STATE["summary"]
        _STATE["computing"] = True
        try:
            if not force and _cache_fresh():
                with open(ENGINE.SUMMARY_JSON, encoding="utf-8") as f:
                    s = json.load(f)
            else:
                s = ENGINE.compute(write=True)
            _STATE.update(summary=s, error=None, loaded_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
            return s
        except Exception as e:
            _STATE["error"] = f"{type(e).__name__}: {e}"
            raise
        finally:
            _STATE["computing"] = False


def warm_up():
    threading.Thread(target=lambda: _safe(get_summary), daemon=True).start()


def _safe(fn):
    try:
        fn()
    except Exception:
        pass


def health():
    s = _STATE["summary"]
    return {"loaded": s is not None, "error": _STATE["error"], "computing": _STATE["computing"],
            "cache_file": ENGINE.SUMMARY_JSON, "cache_fresh": _cache_fresh(),
            "computed_at": s and s.get("computed_at"), "engine_version": ENGINE.ENGINE_VERSION}


def dispatch(method, path, query, body):
    """Returns (status, dict) or None if the path is not a cost route."""
    if path not in ROUTES:
        return None
    if method == "OPTIONS":
        return 204, None
    try:
        if path == "/api/cost/recompute":
            if method != "POST":
                return 405, {"ok": False, "error": "use POST"}
            s = get_summary(force=True)
            return 200, {"ok": True, "computed_at": s["computed_at"], "runtime_s": s["runtime_s"], "totals": s["totals"]}
        if method != "GET":
            return 405, {"ok": False, "error": "use GET"}
        s = get_summary()
        if path == "/api/cost/summary":
            return 200, s
        if path == "/api/cost/live":
            return 200, {"ok": True, "dataset_label": s["dataset_label"], **s["live"]}
        return 200, {"ok": True, "prices": s["prices"], "derived": s["derived"]}
    except Exception as e:
        return 500, {"ok": False, "error": f"{type(e).__name__}: {e}"}


def register_flask_routes(app):
    from flask import Response, request

    def view():
        status, body = dispatch(request.method, request.path, dict(request.args), request.get_data(as_text=True))
        resp = Response("" if body is None else json.dumps(body, ensure_ascii=False, allow_nan=False, default=str),
                        status=status, mimetype="application/json")
        for k, v in CORS.items():
            resp.headers[k] = v
        return resp

    for r in ROUTES:
        app.add_url_rule(r, endpoint="cost_" + r.strip("/").replace("/", "_"), view_func=view,
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
