"""Căutare pe Google Flights (prin fast-flights), comună pentru toate scanerele."""

import re
import time
from datetime import datetime

from fast_flights import FlightData, Passengers
from fast_flights.core import parse_response
from fast_flights.filter import TFSData
from primp import Client

PASSENGERS = dict(adults=2, children=2)
CURRENCY = "EUR"
RETRIES = 2
NONE_RETRIES = 1

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


def build_tfs(legs, trip):
    """legs: [(from, to, date), ...]"""
    return TFSData.from_interface(
        flight_data=[FlightData(date=d.isoformat(), from_airport=a, to_airport=b) for a, b, d in legs],
        trip=trip,
        seat="economy",
        passengers=Passengers(**PASSENGERS),
    ).as_b64().decode()


def google_link(tfs):
    return f"https://www.google.com/travel/flights?tfs={tfs}&hl=ro&curr={CURRENCY}"


def query(legs, trip, max_duration_min=None, keep=5, stay_nights=None):
    """Întoarce {status, link, price_level, options:[...]}; status: ok / none / too_long / error.

    Cu stay_nights, la dus-întors păstrează doar zborurile care aterizează exact cu atâtea
    nopți înainte de zborul de întoarcere.
    """
    tfs = build_tfs(legs, trip)
    out = {"link": google_link(tfs)}

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
            result = parse_response(res)
            break
        except Exception as e:  # noqa: BLE001
            last_error = str(e).splitlines()[0][:200]
            # Pe serverele GitHub, Google dă uneori o pagină fără zboruri pentru rute care au zboruri.
            if "No flights found" in last_error:
                if attempt >= NONE_RETRIES:
                    return {**out, "status": "none", "options": []}
                time.sleep(5)
                continue
            time.sleep(3 * (attempt + 1))
    else:
        return {**out, "status": "error", "error": last_error, "options": []}

    options = []
    seen = set()
    for f in result.flights:
        price = parse_price(f.price)
        minutes = parse_duration(f.duration)
        if not price or minutes is None:
            continue
        if max_duration_min and minutes > max_duration_min:
            continue
        arrives = arrival_date(f.arrival, legs[0][2])
        if stay_nights and (not arrives or (legs[1][2] - arrives).days != stay_nights):
            continue
        key = (f.name, f.departure, f.arrival, price)
        if key in seen:
            continue
        seen.add(key)
        options.append(
            {
                "price": price,
                "duration_min": minutes,
                "stops": f.stops if isinstance(f.stops, int) else None,
                "airlines": f.name,
                "departure": f.departure,
                "arrival": f.arrival,
                "arrival_date": arrives.isoformat() if arrives else None,
            }
        )
    options.sort(key=lambda o: (o["price"], o["duration_min"]))
    return {
        **out,
        "status": "ok" if options else "too_long",
        "price_level": result.current_price or None,
        "options": options[:keep],
    }
