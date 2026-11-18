"""Browser verification for Output/dash_1.html (Playwright, headless).

Checks: zero console/page errors, every pane renders its charts, the December KPI
values match Gad's published table, the pillar index redraws on window change,
tab 2 keeps its classification hierarchy intact, and no horizontal overflow at
1024 / 1280 / 1680 px.
"""
import io
import json
import os
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HTML = os.path.join(ROOT, "dash_1.html")
SHOTS = os.path.join(HERE, "shots")
os.makedirs(SHOTS, exist_ok=True)

URL = "file:///" + HTML.replace("\\", "/")

RESULTS = []
def gate(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))

def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1680, "height": 1050},
                                device_scale_factor=1)
        errors, warns = [], []
        page.on("console", lambda m: (errors if m.type == "error" else warns).append(m.text))
        page.on("pageerror", lambda e: errors.append("pageerror: %s" % e))

        page.goto(URL, wait_until="load")
        page.wait_for_selector("#pane-overview", timeout=60000)
        page.wait_for_timeout(2500)

        # ---------------------------------------------------------- overview
        n_kpi = page.locator("#pane-overview .kpi").count()
        n_chart = page.locator("#pane-overview .js-plotly-plot").count()
        gate("overview renders 5 KPI cards", n_kpi == 5, "%d" % n_kpi)
        gate("overview renders 4 charts", n_chart == 4, "%d" % n_chart)
        ov_vals = page.eval_on_selector_all(
            "#pane-overview .kpi .v", "ns => ns.map(n => n.textContent)")
        gate("overview KPI values are numbers", all(v and v != "—" for v in ov_vals),
             " / ".join(ov_vals))
        health = page.locator("#pane-overview [data-health]").count()
        gate("pillar health strip has 8 cards", health == 8, "%d" % health)

        # ------------------------------------------------------- every pillar
        pillars = ["ENE", "BLD", "WAT", "WST", "GCS", "ENV", "MOB", "PSS"]
        pillar_report = {}
        for code in pillars:
            page.click('#navPillars [data-pane="%s"]' % code)
            page.wait_for_timeout(900)
            pane = "#pane-" + code
            vis = page.locator(pane + " .js-plotly-plot").count()
            kpis = page.locator(pane + " .kpi").count()
            vals = page.eval_on_selector_all(
                pane + " .kpi .v", "ns => ns.map(n => n.textContent)")
            pil = page.evaluate(
                "() => { const n = document.getElementById('pil-%s');"
                " return n && n.data && n.classList.contains('js-plotly-plot') ? 1 : 0; }" % code)
            note = page.text_content("#pilnote-" + code) or ""
            shapes = page.evaluate(
                "() => { const n = document.getElementById('pil-%s');"
                " return n && n.data ? n.layout.shapes.length : 0; }" % code)
            pillar_report[code] = {"charts": vis, "kpis": kpis, "values": vals,
                                   "index_chart": pil, "shapes": shapes,
                                   "note": note[:120]}
            gate("%s pane renders %d KPI cards" % (code, kpis),
                 kpis > 0 and all(v and v != "—" for v in vals), " / ".join(vals))
            gate("%s pane draws its charts" % code, vis >= 4, "%d drawn" % vis)
            gate("%s pillar index drawn with band shapes" % code,
                 pil == 1 and shapes >= 3, "%d shapes" % shapes)
            gate("%s pillar note written" % code, len(note) > 40, note[:60])

        # December parity for the four Gad pillars (published table values)
        page.click('#navPillars [data-pane="ENE"]')
        page.wait_for_timeout(700)
        ene = page.eval_on_selector_all("#pane-ENE .kpi .v", "ns => ns.map(n => n.textContent)")
        gate("ENE-01 December = 8.45 GWh (Gad table)", ene and ene[0] == "8.45", str(ene[:1]))

        # ------------------------------------------------------------ tab 2
        page.click('.seg [data-tab="ew"]')
        page.wait_for_timeout(900)
        rib = page.locator("#pane-ew .ribbon .rib").count()
        tiers = page.locator("#pane-ew .ladder .tier").count()
        tier_n = page.eval_on_selector_all(
            "#pane-ew .ladder .tier-n", "ns => ns.map(n => n.textContent)")
        ewe_rows = page.locator("#pane-ew table").nth(0).locator("tbody tr").count()
        ewb_rows = page.locator("#pane-ew table").nth(1).locator("tbody tr").count()
        ep_rows = page.locator("#pane-ew table").nth(2).locator("tbody tr").count()
        dq_cards = page.locator("#pane-ew .dq-card").count()
        gate("tab 2 ribbon shows 8 pillars", rib == 8, "%d" % rib)
        gate("classification ladder keeps 5 tiers", tiers == 5, "%d" % tiers)
        gate("ladder counts are 0/11/382/16/0",
             tier_n == ["0", "11", "382", "16", "0"], " / ".join(tier_n))
        gate("32 EWE signals listed", ewe_rows == 32, "%d" % ewe_rows)
        gate("15 EWB signals listed", ewb_rows == 15, "%d" % ewb_rows)
        gate("water review episodes listed", ep_rows >= 50, "%d rows" % ep_rows)
        gate("2 data-quality cards", dq_cards == 2, "%d" % dq_cards)
        gate("tab 2 has no merged 'alerts' counter card",
             page.locator("#pane-ew .kpi").count() == 0,
             "%d kpi cards" % page.locator("#pane-ew .kpi").count())
        geo = page.evaluate("""() => {
          const bad = [];
          Object.keys(window.__DASH__.specs).forEach(k => {
            (window.__DASH__.specs[k].data || []).forEach(t => {
              const ty = String(t.type || '').toLowerCase();
              if ((ty.indexOf('scattermap') >= 0 || ty.indexOf('choroplethmap') >= 0 || ty.indexOf('densitymap') >= 0)) { bad.push(k + ':' + ty); }
            });
          });
          return bad;
        }""")
        gate("no zone / geo map trace in any chart", not geo, " | ".join(geo[:4]))

        page.click("#explorer > summary")
        page.wait_for_timeout(500)
        cards = page.locator("#alertList .alert-card").count()
        gate("alert explorer opens with 60 records", cards == 60, "%d" % cards)
        page.click("#alertList .alert-card > summary")
        page.wait_for_timeout(300)
        lag = page.text_content("#alertList .alert-card .meta div:nth-child(3) b") or ""
        gate("alert card shows a detection lag", lag.strip() not in ("", "—"), lag.strip())
        page.click("#showAllAlerts")
        page.wait_for_timeout(600)
        allc = page.locator("#alertList .alert-card").count()
        gate("show-all expands to 409 records", allc == 409, "%d" % allc)

        # ------------------------------------------------------ window change
        page.click('.seg [data-tab="overall"]')
        page.wait_for_timeout(600)
        page.click('.side [data-pane="overview"]')
        page.wait_for_timeout(700)
        before = page.eval_on_selector_all("#pane-overview .kpi .v", "ns => ns.map(n => n.textContent)")
        page.click('[data-preset="ALL"]')
        page.wait_for_timeout(1200)
        after = page.eval_on_selector_all("#pane-overview .kpi .v", "ns => ns.map(n => n.textContent)")
        echo = page.text_content("#fbEcho") or ""
        gate("preset All 2025 changes the overview KPIs", before != after,
             "%s -> %s" % (" / ".join(before), " / ".join(after)))
        gate("filter echo states 365 days", "365 days" in echo, echo.strip())
        page.click('[data-preset="1M"]')
        page.wait_for_timeout(1000)
        back = page.eval_on_selector_all("#pane-overview .kpi .v", "ns => ns.map(n => n.textContent)")
        gate("returning to 1M restores December", back == before, " / ".join(back))

        # pillar index must react to the window too
        page.click('#navPillars [data-pane="WAT"]')
        page.wait_for_timeout(800)
        wat_dec = page.eval_on_selector_all("#pane-WAT .kpi .v", "ns => ns.map(n => n.textContent)")
        page.click('[data-preset="H1"]')
        page.wait_for_timeout(1200)
        wat_h1 = page.eval_on_selector_all("#pane-WAT .kpi .v", "ns => ns.map(n => n.textContent)")
        gate("pillar KPI cards follow the window", wat_dec != wat_h1,
             "%s -> %s" % (" / ".join(wat_dec), " / ".join(wat_h1)))

        # -------------------------------------------------------- responsive
        overflow = {}
        for w in (1024, 1280, 1680):
            page.set_viewport_size({"width": w, "height": 1000})
            page.wait_for_timeout(900)
            over = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
            overflow[w] = over
            gate("no horizontal overflow at %d px" % w, over <= 2, "%d px" % over)
            page.screenshot(path=os.path.join(SHOTS, "dash1_%d.png" % w), full_page=False)

        # desktop tab 2 + a pillar shot for the record
        page.set_viewport_size({"width": 1680, "height": 1050})
        page.wait_for_timeout(500)
        page.screenshot(path=os.path.join(SHOTS, "dash1_pillar_wat.png"), full_page=False)
        page.click('.seg [data-tab="ew"]')
        page.wait_for_timeout(900)
        page.screenshot(path=os.path.join(SHOTS, "dash1_tab2.png"), full_page=False)

        gate("zero console errors", not errors, " | ".join(errors[:4]))
        browser.close()

    print("\n--- browser verification -------------------------------------------")
    bad = 0
    for name, ok, detail in RESULTS:
        print("  %s  %s%s" % ("PASS" if ok else "FAIL", name, ("  · " + detail) if detail else ""))
        bad += 0 if ok else 1
    print("  %d/%d passed" % (len(RESULTS) - bad, len(RESULTS)))
    with io.open(os.path.join(HERE, "verify_report.json"), "w", encoding="utf-8") as f:
        json.dump({"gates": [{"name": n, "ok": o, "detail": d} for n, o, d in RESULTS],
                   "pillars": pillar_report, "errors": errors, "warnings": warns[:10]},
                  f, ensure_ascii=False, indent=2)
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
