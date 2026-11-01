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
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import gf

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
CURRENCY = gf.CURRENCY

WORKERS = 3

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"


def search(origin, dest, dep, nights):
    ret = dep + timedelta(days=nights)
    r = gf.query([(origin, dest, dep), (dest, origin, ret)], "round-trip", MAX_DURATION_MIN)
    return {
        "origin": origin,
        "dest": dest,
        "country": DESTINATIONS[dest]["country"],
        "depart": dep.isoformat(),
        "return": ret.isoformat(),
        "nights": nights,
        **r,
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
    breaker = gf.Breaker()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(search, *c) for c in combos]
        try:
            for i, fut in enumerate(as_completed(futures), 1):
                r = fut.result()
                results.append(r)
                best = r["options"][0]["price"] if r["options"] else "-"
                print(f"[{i}/{len(combos)}] {r['origin']}->{r['dest']} {r['depart']} {r['nights']}n: {r['status']} {best} {r.get('error', '')}", flush=True)
                breaker.record(r)
        except gf.Blocked as e:
            pool.shutdown(wait=False, cancel_futures=True)
            print(f"::error::Scanare oprită, datele vechi rămân: {e}", flush=True)
            return 1

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
