"""Check that BERT is really connected: run with the server already started by run_oasis.bat.

    .venv\\Scripts\\python.exe test_bert.py            (Windows)
    .venv/bin/python test_bert.py                      (macOS / Linux)

1. /api/health: bert_loaded, active engine.
2. Labels: config.json id2label order == model_info.json labels.
3. Five sample complaints (3 Arabic, 2 Franco) through POST /api/classify.
4. The 200-complaint test file (Datasets/TestData/TestBert/oasis_bert_test_complaints_200.csv)
   through POST /api/classify, row by row (the same call the dashboard's batch tab makes):
   accuracy and macro-F1 against expected_category, compared with model_info.json.
Writes everything to bert_test_report.txt. Read-only: nothing is logged by /api/classify.
"""
import csv, json, sys, time, urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
URL = "http://127.0.0.1:5000"
MODEL = HERE / "Moamen" / "oasis_bert_model" / "bert"
TEST = HERE / "Datasets" / "TestData" / "TestBert" / "oasis_bert_test_complaints_200.csv"
OUT = HERE / "bert_test_report.txt"
lines = []


def say(s=""):
    print(s, flush=True); lines.append(s)


def call(path, body=None):
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode("utf-8") if body is not None else None,
                                 headers={"Content-Type": "application/json"} if body is not None else {})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def macro_f1(y, p):
    labels = sorted(set(y) | set(p)); f = []
    for l in labels:
        tp = sum(1 for a, b in zip(y, p) if a == l and b == l)
        fp = sum(1 for a, b in zip(y, p) if a != l and b == l)
        fn = sum(1 for a, b in zip(y, p) if a == l and b != l)
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f.append(2 * pr * rc / (pr + rc) if pr + rc else 0.0)
    return sum(f) / len(f), labels


def main():
    say(f"Oasis BERT connection test - {time.strftime('%Y-%m-%d %H:%M:%S')}  (Python {sys.version.split()[0]})")
    try:
        h = call("/api/health")
    except Exception as e:
        say(f"[ERROR] The server does not answer on {URL}: {e}. Start run_oasis.bat first."); return 1
    say("\n== 1. /api/health")
    for k in ("bert_loaded", "active_engine", "torch_installed", "transformers_installed", "load_error"):
        say(f"  {k:22}: {h.get(k)}")
    if not h.get("bert_loaded"):
        say("[ERROR] BERT is not loaded, so there is nothing to test."); return 1

    say("\n== 2. Label order")
    cfg = json.loads((MODEL / "config.json").read_text(encoding="utf-8"))
    info = json.loads((MODEL / "model_info.json").read_text(encoding="utf-8"))
    order = [cfg["id2label"][str(i)] for i in range(len(cfg["id2label"]))]
    say(f"  config.json id2label == model_info.json labels: {order == info['labels']}  ({len(order)} labels)")

    say("\n== 3. Sample complaints (3 Arabic, 2 Franco)")
    samples = [("ar", "المية مقطوعة من امبارح في العمارة"), ("ar", "الزبالة متكومة جنب المدرسة"), ("ar", "عمود النور مطفي والشارع ضلمة"),
               ("franco", "el kahraba ati3a fel 3emara men sa3tein"), ("franco", "el zebala mtkawema gamb el bawaba")]
    for lang, text in samples:
        t0 = time.time(); r = call("/api/classify", {"text": text}); ms = (time.time() - t0) * 1000
        say(f"  [{lang:6}] {text}\n           -> category={r.get('category')}  confidence={r.get('confidence')}%  engine={r.get('engine')}  ({ms:.0f} ms)")

    say("\n== 4. 200-complaint test file through /api/classify")
    rows = list(csv.DictReader(TEST.open(encoding="utf-8-sig")))
    y, p, engines, t0 = [], [], Counter(), time.time()
    for i, row in enumerate(rows, 1):
        r = call("/api/classify", {"text": row["description_ar"], "zone_id": row.get("zone_id", "")})
        y.append(row["expected_category"].strip()); p.append(r.get("category")); engines[r.get("engine")] += 1
        if i % 50 == 0: print(f"   {i}/{len(rows)}", flush=True)
    acc = sum(a == b for a, b in zip(y, p)) / len(y)
    f1, labels = macro_f1(y, p)
    say(f"  rows: {len(rows)}   engines: {dict(engines)}   time: {time.time() - t0:.1f} s")
    say(f"  accuracy : {acc:.4f}")
    say(f"  macro-F1 : {f1:.4f}   (over the {len(labels)} labels seen in expected or predicted)")
    v = info.get("validation", {})
    say(f"  model_info.json validation (template-grouped split, a different set): accuracy {v.get('accuracy')}, macro-F1 {v.get('macro_f1')}")
    wrong = [(row["description_ar"][:60], a, b) for row, a, b in zip(rows, y, p) if a != b]
    say(f"\n  misclassified: {len(wrong)}")
    for t, a, b in wrong[:40]:
        say(f"    expected {a:16} got {str(b):16} | {t}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nReport written to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
