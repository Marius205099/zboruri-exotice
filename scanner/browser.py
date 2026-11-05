"""Citește Google Flights printr-un browser real, pentru căutările unde cererea directă nu găsește zboruri.

Google trimite uneori o pagină fără zboruri și încarcă rezultatele abia în browser, așa că cererea
directă le-ar trata ca „nu există zbor”. O folosim în continuare prima, pentru că e mult mai rapidă.
"""

import time

from playwright.sync_api import sync_playwright

import gf

PAGE_TIMEOUT_SEC = 30
REFUSED_RETRIES = 2
REFUSED_MAX_BYTES = 1000  # Google răspunde cu un mesaj scurt când refuză cererea
NO_RESULTS = ("No options matching", "No results returned")


class BrowserFetch:
    """Se folosește la fel ca gf.fetch și întoarce același rezultat."""

    def __init__(self):
        self.direct = gf.fetch
        self.pages = self.refused = 0
        self.playwright = sync_playwright().start()
        self.browser = None
        self.open_page()

    def open_page(self):
        if self.browser:
            self.browser.close()
        self.browser = self.playwright.chromium.launch(headless=True, channel="chromium")
        ctx = self.browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900})
        ctx.add_cookies([{"name": k, "value": v, "domain": ".google.com", "path": "/"} for k, v in gf.COOKIES.items()])
        ctx.route("**/*", lambda r: r.abort() if r.request.resource_type in ("image", "font", "media") else r.continue_())
        self.page = ctx.new_page()
        self.page.on("response", self.on_response)

    def close(self):
        self.browser.close()
        self.playwright.stop()

    def on_response(self, response):
        if "GetShoppingResults" in response.url:
            self.answered_at = time.time()
            try:
                self.answer_refused = len(response.body()) < REFUSED_MAX_BYTES
            except Exception:  # noqa: BLE001  pagina a trecut deja la căutarea următoare
                pass

    def has_flights(self):
        return self.page.locator("ul.Rk10dc li span.mv1WYe").count() > 0

    def wait_for_results(self):
        # Pagina Google nu permite wait_for_function, așa că verificăm textul din Python.
        # „No results” apare și cât timp pagina se încarcă, deci contează doar după răspunsul Google.
        end = time.time() + PAGE_TIMEOUT_SEC
        while time.time() < end:
            text = self.page.inner_text("body")
            if "Fetching results" not in text:
                if self.has_flights():
                    return
                if self.answered_at and time.time() - self.answered_at > 2 and any(n in text for n in NO_RESULTS):
                    return
            time.sleep(0.2)
        if not self.has_flights():
            raise TimeoutError("rezultatele nu s-au încărcat")

    def load(self, tfs):
        self.pages += 1
        self.answered_at, self.answer_refused = None, False
        self.page.goto(f"https://www.google.com/travel/flights?tfs={tfs}&hl=en&curr={gf.CURRENCY}", wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_SEC * 1000)
        self.wait_for_results()
        return gf.parse_flights(self.page.content())

    def __call__(self, tfs):
        result = self.direct(tfs)
        if result[0] == "ok":
            return result

        error = None
        for attempt in range(REFUSED_RETRIES + 1):
            try:
                flights, level = self.load(tfs)
                if flights:
                    return "ok", flights, level, None
                if not self.answer_refused:
                    return "none", [], None, None
                self.refused += 1
                error = "Google a refuzat cererea"
            except Exception as e:  # noqa: BLE001
                error = str(e).splitlines()[0][:200]
                try:
                    self.open_page()
                except Exception as restart:  # noqa: BLE001
                    error = str(restart).splitlines()[0][:200]
            time.sleep(3 * (attempt + 1))
        return "error", [], None, error
