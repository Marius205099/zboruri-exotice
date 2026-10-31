"""Scaner de zboruri dus-întors pentru vacanța de iarnă 2026/2027.

Caută pe Google Flights (prin biblioteca fast-flights) toate combinațiile:
  plecare din TSR / CLJ / BUD / BEG
  către Maldive, Bali, Thailanda, Mauritius
  plecare 26 dec 2026 – 3 ian 2027, sejur 7–9 nopți
  2 adulți + 2 copii (3 și 5 ani)
și păstrează doar zborurile cu durata dus de maxim 25 de ore.

Rezultatul se scrie în docs/data/results.json (citit de site),
iar istoricul celor mai bune prețuri în docs/data/history.json.
"""

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fast_flights import FlightData, Passengers
from fast_flights.core import parse_response
from fast_flights.filter import TFSData
from primp import Client

ORIGINS = {
    "TSR": "Timișoara",
    "CLJ": "Cluj-Napoca",
    "BUD": "Budapesta",
    "BEG": "Belgrad",
}

DESTINATIONS = {
    "MLE": {"city": "Malé", "country": "Maldive"},
    "DPS": {"city": "Denpasar", "country": "Bali"},
    "BKK": {"city": "Bangkok", "country": "Thailanda"},
    "HKT": {"city": "Phuket", "country": "Thailanda"},
    "MRU": {"city": "Port Louis", "country": "Mauritius"},
}

FIRST_DEPARTURE = date(2026, 12, 26)
LAST_DEPARTURE = date(2027, 1, 3)
NIGHTS = (7, 8, 9)
MAX_DURATION_MIN = 25 * 60
PASSENGERS = dict(adults=2, children=2)
CURRENCY = "EUR"

WORKERS = 3
RETRIES = 2

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"

# Cookie de consimțământ Google, ca să nu primim pagina de cookie-uri din UE.
COOKIES = {"SOCS": "CAESEwgDEgk0ODE3Nzk3MjQaAmVuIAEaBgiA_LyaBg"}


def build_filter(origin, dest, dep, ret):
    return TFSData.from_interface(
        flight_data=[
            FlightData(date=dep.isoformat(), from_airport=origin, to_airport=dest),
            FlightData(date=ret.isoformat(), from_airport=dest, to_airport=origin),
        ],
        trip="round-trip",
        seat="economy",
        passengers=Passengers(**PASSENGERS),
    )


def google_link(tfs_b64):
    return f"https://www.google.com/travel/flights?tfs={tfs_b64}&hl=ro&curr={CURRENCY}"


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


def search(origin, dest, dep, nights):
    ret = dep + timedelta(days=nights)
    tfs = build_filter(origin, dest, dep, ret).as_b64().decode()
    combo = {
        "origin": origin,
        "dest": dest,
        "country": DESTINATIONS[dest]["country"],
        "depart": dep.isoformat(),
        "return": ret.isoformat(),
        "nights": nights,
        "link": google_link(tfs),
    }

    last_error = None
    for attempt in range(RETRIES + 1):
        try:
            client = Client(impersonate="chrome_126")
            res = client.get(
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
            if "No flights found" in last_error:
                return {**combo, "status": "none", "options": []}
            time.sleep(3 * (attempt + 1))
    else:
        return {**combo, "status": "error", "error": last_error, "options": []}

    options = []
    seen = set()
    for f in result.flights:
        price = parse_price(f.price)
        minutes = parse_duration(f.duration)
        if not price or minutes is None or minutes > MAX_DURATION_MIN:
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
            }
        )
    options.sort(key=lambda o: (o["price"], o["duration_min"]))
    return {
        **combo,
        "status": "ok" if options else "too_long",
        "price_level": result.current_price or None,
        "options": options[:5],
    }


def all_combos():
    d = FIRST_DEPARTURE
    while d <= LAST_DEPARTURE:
        for origin in ORIGINS:
            for dest in DESTINATIONS:
                for n in NIGHTS:
                    yield origin, dest, d, n
        d += timedelta(days=1)


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    combos = list(all_combos())[:limit]
    started = datetime.now(timezone.utc)
    print(f"Scanez {len(combos)} combinații…", flush=True)

    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(search, *c) for c in combos]
        for i, fut in enumerate(as_completed(futures), 1):
            r = fut.result()
            results.append(r)
            best = r["options"][0]["price"] if r["options"] else "-"
            print(f"[{i}/{len(combos)}] {r['origin']}->{r['dest']} {r['depart']} {r['nights']}n: {r['status']} {best}", flush=True)

    results.sort(key=lambda r: (r["options"][0]["price"] if r["options"] else 10**9))
    ok = [r for r in results if r["options"]]
    errors = sum(1 for r in results if r["status"] == "error")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "results.json"

    # Dacă scanarea a eșuat aproape complet (ex. blocare temporară), păstrăm datele vechi.
    if len(results) > 20 and errors > 0.8 * len(results) and out_path.exists():
        print(f"Prea multe erori ({errors}/{len(results)}), păstrez rezultatele anterioare.")
        return 1

    payload = {
        "scanned_at": started.isoformat(timespec="seconds"),
        "duration_sec": int((datetime.now(timezone.utc) - started).total_seconds()),
        "currency": CURRENCY,
        "passengers": "2 adulți + 2 copii (3 și 5 ani)",
        "max_duration_h": MAX_DURATION_MIN // 60,
        "origins": ORIGINS,
        "destinations": DESTINATIONS,
        "stats": {"total": len(results), "with_price": len(ok), "errors": errors},
        "results": results,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1))

    hist_path = DATA_DIR / "history.json"
    history = json.loads(hist_path.read_text()) if hist_path.exists() else []
    entry = {"t": payload["scanned_at"], "best": {}}
    for r in ok:
        c = r["country"]
        p = r["options"][0]["price"]
        if c not in entry["best"] or p < entry["best"][c]:
            entry["best"][c] = p
    history.append(entry)
    hist_path.write_text(json.dumps(history[-120:], ensure_ascii=False))

    print(f"Gata: {len(ok)} cu preț, {errors} erori, în {payload['duration_sec']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
