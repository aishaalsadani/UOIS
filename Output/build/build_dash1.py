"""Assemble the single-file dashboard: Output/dash_1.html

Inputs (all produced by extract_dash1.py / written by hand):
  Output/build/parts/shell.html    markup skeleton with four placeholders
  Output/build/parts/style.css     design tokens + component CSS
  Output/build/parts/app.js        client application (pillar engine + views)
  Output/build/dash1_data.json     the payload
  Gad/outputs/figures/Oasis_Energy_Buildings_Dashboard_v2.html   inline plotly.js bundle

Output: Output/dash_1.html  (one file, no <script src>, no network calls)
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # ...\Code\Tasks\Output
TASKS = os.path.dirname(ROOT)                      # ...\Code\Tasks
GAD = os.path.join(TASKS, "Gad", "outputs", "figures",
                   "Oasis_Energy_Buildings_Dashboard_v2.html")
OUT = os.path.join(ROOT, "dash_1.html")

def log(m):
    print(m, flush=True)

def read(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read()

# ---------------------------------------------------------------- plotly bundle
def plotly_bundle():
    html = read(GAD)
    blocks = re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.S | re.I)
    if not blocks:
        raise SystemExit("no <script> block found in %s" % GAD)
    blocks.sort(key=len, reverse=True)
    js = blocks[0]
    if "Plotly" not in js or len(js) < 1_000_000:
        raise SystemExit("largest script block does not look like the plotly bundle "
                         "(len=%d)" % len(js))
    ver = re.search(r"plotly\.js v([0-9.]+)", js)
    log("plotly bundle: %.2f MB%s" % (len(js) / 1e6, (" · v" + ver.group(1)) if ver else ""))
    return js

# ---------------------------------------------------------------------- payload
def payload():
    path = os.path.join(HERE, "dash1_data.json")
    raw = read(path)
    data = json.loads(raw)
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # a JSON string must never be able to close the inline <script>
    raw = raw.replace("</", "<\\/")
    log("payload: %.2f MB · %d series · %d specs · %d pillars · %d alerts"
        % (len(raw.encode("utf-8")) / 1e6, len(data["series"]), len(data["specs"]),
           len(data["pillars"]), len(data["tab2"]["alerts"])))
    return raw, data

def main():
    shell = read(os.path.join(HERE, "parts", "shell.html"))
    css = read(os.path.join(HERE, "parts", "style.css"))
    app = read(os.path.join(HERE, "parts", "app.js"))
    js = plotly_bundle()
    data_raw, data = payload()

    for marker in ("/*__STYLE__*/", "/*__PLOTLY__*/", "/*__DATA__*/", "/*__APP__*/"):
        if marker not in shell:
            raise SystemExit("placeholder missing from shell.html: %s" % marker)

    html = (shell
            .replace("/*__STYLE__*/", css)
            .replace("/*__PLOTLY__*/", js)
            .replace("/*__DATA__*/", data_raw)
            .replace("/*__APP__*/", app))

    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)

    size = os.path.getsize(OUT)
    log("\nwrote %s  (%.2f MB)" % (OUT, size / 1e6))

    # ---------------------------------------------------------------- gates
    gates = []
    def gate(name, ok, detail=""):
        gates.append((name, bool(ok), detail))

    gate("single file, no <script src>", not re.search(r"<script[^>]+\bsrc\s*=", html, re.I))
    gate("no <link rel=stylesheet>", not re.search(r"<link[^>]+rel=[\"']?stylesheet", html, re.I))
    gate("no @import / url(http)", not re.search(r"@import|url\(\s*['\"]?https?:", html, re.I))
    gate("plotly inline present once", html.count("Plotly, Inc") >= 1 and
         len(re.findall(r"plotly\.js v[0-9.]+", html)) >= 1)
    gate("payload injected", "window.__DASH__" in html and '"pillars"' in html)
    gate("no leftover placeholder", not re.search(r"/\*__[A-Z]+__\*/", html))
    gate("disclaimer present", html.count("Synthetic — for training only") >= 2)
    gate("tabular-nums declared", "font-variant-numeric: tabular-nums" in html)
    gate("8 pillars in payload", len(data["pillars"]) == 8)
    gate("chart specs >= 36", len(data["specs"]) >= 36)
    gate("file opens standalone (< 12 MB)", size < 12_000_000, "%.2f MB" % (size / 1e6))

    log("\n--- build gates ----------------------------------------------------")
    bad = 0
    for name, ok, detail in gates:
        log("  %s  %s%s" % ("PASS" if ok else "FAIL", name, ("  · " + detail) if detail else ""))
        bad += 0 if ok else 1
    log("  %d/%d passed" % (len(gates) - bad, len(gates)))
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
