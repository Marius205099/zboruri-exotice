"""Test mic: citim Google Flights printr-un browser real, în loc de cererea directă din gf.py?

Nu schimbă scanarea și nu atinge site-ul. Rezultatele ajung în test-results/browser-test.json.
Cazul „zboruri ratate”: cererea directă întoarce o pagină fără zboruri, browserul găsește zboruri.
"""

import json
import os
import random
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scanner"))

from playwright.sync_api import sync_playwright  # noqa: E402

import gf  # noqa: E402
import scan  # noqa: E402

OUT = ROOT / "test-results" / "browser-test.json"
BUDGET_SEC = int(os.environ.get("BUDGET_SEC", 20 * 60))
SAMPLE = int(os.environ.get("SAMPLE", 28))
PAGE_TIMEOUT_MS = 30000

# Verificate manual în browser pe 4–5 nov. 2026.
KNOWN = [
    ("exista", "BEG", "HKT", date(2027, 8, 11), 8),
    ("exista", "BEG", "MLE", date(2027, 8, 31), 9),
    ("exista", "CLJ", "MLE", date(2027, 6, 9), 7),
    ("exista", "BEG", "DPS", date(2027, 6, 25), 9),
    ("exista", "BEG", "HKT", date(2027, 3, 10), 8),
    ("nu_exista", "TSR", "HKT", date(2027, 1, 20), 8),
    ("nu_exista", "CLJ", "HKT", date(2027, 4, 14), 8),
]


def legs_of(a, b, d, n):
    return [(a, b, d), (b, a, d + timedelta(days=n))]


def sample_missing():
    """Căutări din scanare fără preț pe site, aceeași pondere pentru fiecare oraș."""
    data = json.loads((ROOT / "docs" / "data" / "results.json").read_text())
    have = {(r["origin"], r["dest"], r["depart"], r["return"]) for r in data["results"]}
    missing = {o: [] for o in scan.ORIGINS}
    for o, dest, d, n in scan.all_combos():
        if (o, dest, d.isoformat(), (d + timedelta(days=n)).isoformat()) not in have:
            missing[o].append(("esantion", o, dest, d, n))
    rng = random.Random(11)
    per_origin = SAMPLE // len(missing)
    return [c for items in missing.values() for c in rng.sample(items, min(per_origin, len(items)))]


class BrowserFetch:
    """Același rezultat ca gf.fetch, dar pagina e încărcată într-un browser real."""

    def __init__(self, page):
        self.page = page
        self.last_answer = None
        self.refused = False
        page.on("response", self.on_response)

    def on_response(self, response):
        if "GetShoppingResults" in response.url:
            self.last_answer = time.time()
            self.refused = len(response.body()) < 1000  # Google răspunde cu un mesaj scurt când refuză cererea

    def wait_for_results(self):
        # Pagina Google nu permite wait_for_function, așa că verificăm textul din Python.
        # „No results” apare și cât timp pagina se încarcă, deci contează doar după răspunsul Google.
        end = time.time() + PAGE_TIMEOUT_MS / 1000
        while time.time() < end:
            text = self.page.inner_text("body")
            if "Fetching results" not in text:
                if self.page.locator("ul.Rk10dc li span.mv1WYe").count():
                    return
                answered = self.last_answer and time.time() - self.last_answer > 2
                if answered and ("No options matching" in text or "No results returned" in text):
                    return
            time.sleep(0.2)
        raise TimeoutError("rezultatele nu s-au încărcat")

    def __call__(self, tfs):
        self.last_answer = None
        self.refused = False
        try:
            self.page.goto(gf.google_link(tfs).replace("hl=ro", "hl=en"), wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
            self.wait_for_results()
            html = self.page.content()
        except Exception as e:  # noqa: BLE001
            return "error", [], None, f"{self.page.url[:60]} {str(e).splitlines()[0][:120]}"
        flights, level = gf.parse_flights(html)
        return ("ok" if flights else "none"), flights, level, None


def main():
    http_fetch = gf.fetch
    cases = KNOWN + sample_missing()
    started = time.time()
    report = {"started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "cases": [], "finished": False}

    def save():
        report["elapsed_sec"] = int(time.time() - started)
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chromium")
        ctx = browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900})
        ctx.add_cookies([{"name": k, "value": v, "domain": ".google.com", "path": "/"} for k, v in gf.COOKIES.items()])
        ctx.route("**/*", lambda r: r.abort() if r.request.resource_type in ("image", "font", "media") else r.continue_())
        page = ctx.new_page()
        browser_fetch = BrowserFetch(page)

        for kind, a, b, d, n in cases:
            if time.time() - started > BUDGET_SEC:
                break
            tfs = gf.build_tfs(legs_of(a, b, d, n), "round-trip", scan.MAX_STOPS)
            http_status = http_fetch(tfs)[0]

            t = time.time()
            status, flights, _, error = browser_fetch(tfs)
            row = {
                "kind": kind, "route": f"{a}-{b}", "date": d.isoformat(), "days": n,
                "http": http_status, "browser": status, "flights": len(flights), "refused": browser_fetch.refused,
                "page_sec": round(time.time() - t, 1), "error": error,
            }
            # Fluxul complet al scanării: filtrele de 20h și 7 nopți, apoi returul pentru fiecare zbor ales.
            if flights:
                gf.fetch = browser_fetch
                t = time.time()
                r = scan.search(a, b, d, n)
                gf.fetch = http_fetch
                o = r["options"][0] if r["options"] else None
                row.update(
                    query_status=r["status"], query_sec=round(time.time() - t, 1),
                    price=o and o["price"], outbound_min=o and o["duration_min"],
                    return_min=o and o["return_flight"]["duration_min"], airlines=o and o["airlines"],
                )
            report["cases"].append(row)
            print(row, flush=True)
            save()
        browser.close()

    report["finished"] = True
    save()


if __name__ == "__main__":
    main()
