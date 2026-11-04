"""Căutare pe Google Flights, comună pentru toate scanerele."""

import base64
import re
import time
from datetime import datetime

from primp import Client
from selectolax.lexbor import LexborHTMLParser

PASSENGERS = bytes([1, 1, 2, 2])  # 2 adulți + 2 copii
CURRENCY = "EUR"
RETRIES = 2
NONE_RETRIES = 1

# Prețurile low-cost de pe Google Flights nu includ bagajul de cală.
LOW_COST = ("Wizz", "Ryanair", "easyJet", "Pegasus", "flydubai", "Air Arabia", "Vueling",
            "Transavia", "Eurowings", "AJet", "Volotea", "SkyUp", "HiSky", "Norse", "Scoot", "AirAsia")
# Low-cost care transferă bagajele între zborurile de pe același bilet.
THROUGH_LOW_COST = ("flydubai",)

# Cookie de consimțământ Google, ca să nu primim pagina de cookie-uri din UE.
COOKIES = {"SOCS": "CAESEwgDEgk0ODE3Nzk3MjQaAmVuIAEaBgiA_LyaBg"}


class Blocked(Exception):
    """Prea multe erori consecutive: Google refuză cererile, nu are rost să continuăm."""


class Breaker:
    def __init__(self, limit=30):
        self.limit, self.streak = limit, 0

    def record(self, result):
        self.streak = self.streak + 1 if result["status"] == "error" else 0
        if self.streak >= self.limit:
            raise Blocked(f"{self.limit} erori consecutive, ultima: {result.get('error')}")


def parse_duration(text):
    """'23 hr 45 min' -> 1425"""
    h = re.search(r"(\d+)\s*hr", text)
    m = re.search(r"(\d+)\s*min", text)
    if not h and not m:
        return None
    return (int(h.group(1)) if h else 0) * 60 + (int(m.group(1)) if m else 0)


def parse_price(text):
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def arrival_date(text, departure):
    """'2:20 PM on Sun, Jan 3' -> data aterizării (anul se deduce din data plecării)."""
    m = re.search(r"on \w+, (\w+) (\d+)", text or "")
    if not m:
        return None
    d = datetime.strptime(f"{m.group(1)} {m.group(2)} {departure.year}", "%b %d %Y").date()
    return d if d >= departure else d.replace(year=departure.year + 1)


def bag_transfer(stops, airlines):
    """'auto' pentru un bilet cu transfer de bagaje; 'verify' dacă escala implică un low-cost fără transfer sigur."""
    if stops == 0:
        return "auto"
    for name in (airlines or "").split(","):
        name = name.lower()
        if any(lc.lower() in name for lc in LOW_COST) and not any(t.lower() in name for t in THROUGH_LOW_COST):
            return "verify"
    return "auto"


def _varint(n):
    out = b""
    while n > 127:
        out += bytes([n & 127 | 128])
        n >>= 7
    return out + bytes([n])


def _num(field, value):
    return _varint(field << 3) + _varint(value)


def _text(field, value):
    value = value if isinstance(value, bytes) else value.encode()
    return _varint(field << 3 | 2) + _varint(len(value)) + value


def build_tfs(legs, trip, max_stops=None, selected=()):
    """legs: [(from, to, date), ...]; selected: segmentele zborurilor deja alese, pentru fiecare leg."""
    info = b""
    for i, (a, b, d) in enumerate(legs):
        leg = _text(2, d.isoformat())
        for s in selected[i] if i < len(selected) else ():
            leg += _text(4, _text(1, s["from"]) + _text(2, s["date"]) + _text(3, s["to"]) + _text(5, s["airline"]) + _text(6, s["number"]))
        if max_stops is not None:
            leg += _num(5, max_stops)
        info += _text(3, leg + _text(13, _text(2, a)) + _text(14, _text(2, b)))
    info += _text(8, PASSENGERS) + _num(9, 1) + _num(19, 1 if trip == "round-trip" else 2)
    return base64.urlsafe_b64encode(info).decode().rstrip("=")


def google_link(tfs):
    return f"https://www.google.com/travel/flights?tfs={tfs}&hl=ro&curr={CURRENCY}"


def parse_segments(itinerary):
    """'BEG-DOH-QR-232-20270103,DOH-HKT-QR-842-20270103' -> segmentele zborului."""
    segments = []
    for part in itinerary.split(","):
        a, b, airline, number, d = part.split("-")
        segments.append({"from": a, "to": b, "airline": airline, "number": number, "date": f"{d[:4]}-{d[4:6]}-{d[6:]}"})
    return segments


def parse_flights(html):
    """Zborurile din pagina Google Flights, cu segmentele fiecăruia."""
    tree = LexborHTMLParser(html)
    flights = []
    for group in tree.css('div[jsname="IWWDBc"], div[jsname="YdtKid"]'):
        for item in group.css("ul.Rk10dc li"):
            itinerary = re.search(r'itinerary=([^"&]+)', item.html)
            times = item.css("span.mv1WYe div")
            if not itinerary or len(times) < 2:
                continue
            text = lambda css: (item.css_first(css).text(strip=True) if item.css_first(css) else "")  # noqa: E731
            stops = text(".BbR8Ec .ogfYpf")
            flights.append(
                {
                    "name": text("div.sSHqwe.tPgKwe.ogfYpf span"),
                    "departure": " ".join(times[0].text(strip=True).split()),
                    "arrival": " ".join(times[1].text(strip=True).split()),
                    "duration": text("li div.Ak5kof div"),
                    "stops": 0 if stops == "Nonstop" else int(stops.split()[0]) if stops[:1].isdigit() else None,
                    "price": text(".YMlIz.FpEdX"),
                    "segments": parse_segments(itinerary.group(1)),
                }
            )
    level = tree.css_first("span.gOatQ")
    return flights, level.text() if level else None


def fetch(tfs):
    """Întoarce (status, zboruri, nivel de preț, eroare); status: ok / none / error."""
    last_error = None
    for attempt in range(RETRIES + 1):
        try:
            res = Client(impersonate="chrome_126").get(
                "https://www.google.com/travel/flights",
                params={"tfs": tfs, "hl": "en", "tfu": "EgQIABABIgA", "curr": CURRENCY},
                cookies=COOKIES,
            )
            if res.status_code != 200:
                raise RuntimeError(f"HTTP {res.status_code}")
            flights, level = parse_flights(res.text)
            if flights:
                return "ok", flights, level, None
            # Pe serverele GitHub, Google dă uneori o pagină fără zboruri pentru rute care au zboruri.
            if attempt >= NONE_RETRIES:
                return "none", [], None, None
            time.sleep(5)
        except Exception as e:  # noqa: BLE001
            last_error = str(e).splitlines()[0][:200]
            time.sleep(3 * (attempt + 1))
    return "error", [], None, last_error


def describe(f, departure):
    """Detaliile afișate pentru un zbor; None dacă nu respectă cerințele de bază."""
    price = parse_price(f["price"])
    minutes = parse_duration(f["duration"])
    # Biletele separate ascunse într-un singur rezultat înseamnă transfer manual nevizibil pe site.
    if not price or minutes is None or "Separate tickets" in f["name"]:
        return None
    arrives = arrival_date(f["arrival"], departure)
    return {
        "price": price,
        "duration_min": minutes,
        "stops": f["stops"],
        "airlines": f["name"],
        "bag_transfer": bag_transfer(f["stops"], f["name"]),
        "departure": f["departure"],
        "arrival": f["arrival"],
        "arrival_date": arrives.isoformat() if arrives else None,
        "via": [s["to"] for s in f["segments"][:-1]],
        "flights": [f'{s["airline"]} {s["number"]}' for s in f["segments"]],
    }


def within(o, max_duration_min, max_stops):
    if max_duration_min and o["duration_min"] > max_duration_min:
        return False
    return max_stops is None or (o["stops"] is not None and o["stops"] <= max_stops)


def cheapest_return(legs, outbound, max_duration_min, max_stops):
    """Cel mai ieftin retur care respectă limitele, după alegerea zborului dus."""
    tfs = build_tfs(legs, "round-trip", max_stops, [outbound])
    status, flights, _, error = fetch(tfs)
    if status == "error":
        return None, error
    best = None
    for f in flights:
        o = describe(f, legs[1][2])
        if not o or not o["arrival_date"] or not within(o, max_duration_min, max_stops):
            continue
        if not best or (o["price"], o["duration_min"]) < (best[0]["price"], best[0]["duration_min"]):
            best = (o, f["segments"])
    return best, None


def query(legs, trip, max_duration_min=None, keep=5, stay_nights=None, max_stops=None, return_max_duration_min=None, tries=None):
    """Întoarce {status, link, price_level, options:[...]}; status: ok / none / too_long / error.

    Cu stay_nights, la dus-întors păstrează doar zborurile care aterizează exact cu atâtea
    nopți înainte de zborul de întoarcere. Cu max_stops, păstrează doar zborurile cu cel mult
    atâtea escale. La dus-întors caută și returul fiecărui zbor dus (cel mult `tries` zboruri),
    iar prețul opțiunii este cel al biletului cu tot cu acel retur.
    """
    tfs = build_tfs(legs, trip, max_stops)
    out = {"link": google_link(tfs)}

    status, flights, level, error = fetch(tfs)
    if status == "error":
        return {**out, "status": "error", "error": error, "options": []}
    if status == "none":
        return {**out, "status": "none", "options": []}

    candidates = []
    seen = set()
    for f in flights:
        o = describe(f, legs[0][2])
        if not o or not within(o, max_duration_min, max_stops):
            continue
        arrives = o["arrival_date"]
        if stay_nights and (not arrives or (legs[1][2] - datetime.fromisoformat(arrives).date()).days != stay_nights):
            continue
        key = (f["name"], f["departure"], f["arrival"])
        if key in seen:
            continue
        seen.add(key)
        candidates.append((o, f["segments"]))
    candidates.sort(key=lambda c: (c[0]["price"], c[0]["duration_min"]))

    if trip != "round-trip":
        options = [c[0] for c in candidates]
    else:
        options, errors = [], 0
        for o, segments in candidates[:tries or keep]:
            found, error = cheapest_return(legs, segments, return_max_duration_min, max_stops)
            errors += error is not None
            if not found:
                continue
            back, back_segments = found
            options.append(
                {
                    **o,
                    "price": back["price"],
                    "bag_transfer": "auto" if o["bag_transfer"] == back["bag_transfer"] == "auto" else "verify",
                    "link": google_link(build_tfs(legs, trip, max_stops, [segments, back_segments])),
                    "return_flight": {k: v for k, v in back.items() if k != "price"},
                }
            )
            if len(options) >= keep:
                break
        if not options and errors:
            return {**out, "status": "error", "error": error, "options": []}
    options.sort(key=lambda o: (o["price"], o["duration_min"]))
    return {
        **out,
        "status": "ok" if options else "too_long",
        "price_level": level or None,
        "options": options[:keep],
    }
