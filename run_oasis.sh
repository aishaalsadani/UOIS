#!/usr/bin/env bash
# UOIS - Urban Operations Intelligence System - launcher (macOS / Linux): server + BERT + dashboard
# Uses a project virtual environment .venv with Python 3.13 -> 3.12 -> 3.11 -> 3.10.
# Python 3.14+ is never used (pyyaml / torch wheels are missing there).
set -u
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"
URL="http://127.0.0.1:5000"
VENV="$DIR/.venv"
VPY="$VENV/bin/python"
red() { printf '\033[91m%s\033[0m\n' "$*"; }
green() { printf '\033[92m%s\033[0m\n' "$*"; }
supported() { "$1" -c 'import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)' >/dev/null 2>&1; }

echo "==============================================================================="
echo "  UOIS - Urban Operations Intelligence System: server + BERT + dashboard"
echo "==============================================================================="

# 1. Python environment
echo "[1/5] Python environment (.venv with Python 3.13 / 3.12 / 3.11 / 3.10)..."
if [ -x "$VPY" ]; then
  if ! supported "$VPY"; then
    red "[ERROR] The existing .venv uses an unsupported Python (not 3.10-3.13)."
    red "        Rename the .venv folder (for example to .venv_old) and run run_oasis.sh again."
    exit 1
  fi
else
  BASE="${PY_BIN:-}"
  if [ -n "$BASE" ] && ! supported "$BASE"; then red "[ERROR] PY_BIN=$BASE is not Python 3.10-3.13."; exit 1; fi
  if [ -z "$BASE" ]; then
    for c in python3.13 python3.12 python3.11 python3.10 python3 python; do
      if command -v "$c" >/dev/null 2>&1 && supported "$c"; then BASE="$c"; break; fi
    done
  fi
  if [ -z "$BASE" ]; then
    red "[ERROR] No Python 3.13, 3.12, 3.11 or 3.10 was found (Python 3.14 and newer are not supported)."
    echo "  Install Python 3.13, then run run_oasis.sh again."
    echo "  The data pages still work without Python: open oasis_city_system.html directly."
    exit 1
  fi
  echo "  creating .venv with $("$BASE" --version 2>&1) ($BASE)"
  if ! "$BASE" -m venv "$VENV"; then red "[ERROR] Could not create .venv with $BASE."; exit 1; fi
fi
echo "  using $("$VPY" --version 2>&1) (.venv/bin/python)"

# 2. requirements
echo "[2/5] Checking requirements (flask, torch CPU, transformers, pyyaml)..."
if ! "$VPY" -c "import flask, torch, transformers, safetensors, yaml" >/dev/null 2>&1; then
  echo "  Missing packages. Installing requirements.txt into .venv (first run only)."
  echo "  CPU-only PyTorch + transformers: about 150 MB download (Windows/Linux CPU wheels), about 620 MB on disk."
  if ! "$VPY" install_requirements.py; then
    red "[ERROR] Installing the requirements failed (the real pip error is printed above in red)."
    red "        The server was NOT started. Fix the error above, then run run_oasis.sh again."
    exit 1
  fi
else
  echo "  all present."
fi
# Decision Lab (added): numpy, pandas, scipy for Ayat's 60-day simulator, pytest for tests/. Optional.
if ! "$VPY" -c "import numpy, pandas, scipy, pytest" >/dev/null 2>&1; then
  echo "  Installing the Decision Lab packages (numpy, pandas, scipy, pytest) into .venv (once)..."
  "$VPY" install_requirements.py --groups simulator,tests || red "  [WARNING] Decision Lab packages not installed; the server starts without the simulator."
fi

health() { curl -s -m 2 "$URL/api/health"; }

# 3. start server
echo "[3/5] Starting citizen_app.py on $URL ..."
SERVER_PID=""
if [ -n "$(health 2>/dev/null)" ]; then
  if health | "$VPY" -c "import sys, json; sys.exit(0 if json.load(sys.stdin).get('bert_loaded') else 1)"; then
    echo "  a server with BERT loaded is already answering on port 5000; using it."
  else
    red "[ERROR] Another server is already running on port 5000 and it has NOT loaded BERT."
    red "        Stop it, then run run_oasis.sh again."
    exit 1
  fi
else
  "$VPY" -u citizen_app.py > server.log 2>&1 &
  SERVER_PID=$!
  echo "  server pid $SERVER_PID (log: server.log)"
  trap 'kill $SERVER_PID 2>/dev/null' INT TERM
fi

# 4. wait for /api/health
echo "[4/5] Waiting for the server to answer (loading BERT can take up to a minute)..."
for i in $(seq 1 90); do
  if [ -n "$(health 2>/dev/null)" ]; then break; fi
  if [ "$i" -eq 90 ]; then red "[ERROR] No answer after about 3 minutes. See server.log."; exit 1; fi
  sleep 2
done
echo "  server is up."
echo "---------------------------------------------------------------- model report"
echo "  Python                 : $("$VPY" --version 2>&1) (.venv)"
health | "$VPY" -c '
import json, sys
h = json.load(sys.stdin)
R, G, O = "\033[91m", "\033[92m", "\033[0m"
print("  PyTorch installed      :", h.get("torch_installed"))
print("  transformers installed :", h.get("transformers_installed"))
for k, v in (h.get("model_files") or {}).items():
    print("  model file %-22s: %s" % (k, v))
if h.get("bert_loaded"):
    print(G + "  INFERENCE_ENGINE       : BERT model LOADED (MARBERTv2 fine-tuned)" + O)
else:
    print(R + "  INFERENCE_ENGINE       : FELL BACK to the keyword classifier - BERT is NOT loaded" + O)
    print(R + "  reason                 : " + str(h.get("load_error")) + O)
    print(R + "  The dashboard will show no classification results until BERT loads." + O)
s = h.get("simulator_60d") or {}
if s.get("loaded"):
    print(G + "  Simulator 60d          : LOADED (%s draws, %s to %s) - Decision Lab ready" % (s.get("n_sims"), *(s.get("dates") or ["?", "?"])) + O)
else:
    print(R + "  Simulator 60d          : NOT loaded - the Decision Lab page will show the offline message" + O)
    print(R + "  reason                 : " + str(s.get("error")) + O)
if not h.get("dashboard_file"):
    print("  [WARNING] oasis_city_system.html not found next to citizen_app.py or one folder up.")
'
echo "-------------------------------------------------------------------------------"

# 5. open the dashboard
echo "[5/5] Opening $URL/dashboard ..."
if command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL/dashboard" >/dev/null 2>&1 &
elif command -v open >/dev/null 2>&1; then open "$URL/dashboard"
else echo "  -> open $URL/dashboard in your browser."; fi
echo "  Original pages still served: /portal  /model-analytics  /forecast (dash_1 forecast)"
if [ -n "$SERVER_PID" ]; then echo "  Press Ctrl+C to stop the server."; wait "$SERVER_PID"; fi
