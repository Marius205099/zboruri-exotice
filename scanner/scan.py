"""Scaner de zboruri dus-întors.

Caută pe Google Flights (biletele cu o singură rezervare) toate combinațiile:
  plecare din TSR / CLJ / BUD / BEG
  către Maldive, Bali, Thailanda (Phuket), Mauritius
  plecare de azi până pe 10 ian 2028, retur până pe 18 ian 2028, 7 nopți de cazare
  2 adulți + 2 copii (3 și 5 ani)
și păstrează doar biletele cu zbor dus și retur de maxim 20 de ore, cu cel mult o escală.

Cele 7 nopți se numără de la aterizare: plecare 10 ian, aterizare 11 ian, retur 18 ian.
De aceea căutăm returul la 7, 8 și 9 zile de la plecare și păstrăm doar zborurile
care aterizează exact cu 7 nopți înainte de retur.

Google arată zboruri cu cel mult 330 de zile înainte, deci datele mai îndepărtate
intră automat în scanare pe măsură ce se apropie.

Perioada e lungă, așa că scanarea se împarte pe joburi paralele:
  python scanner/scan.py 0 20     # partea 0 din 20, scrisă în parts/
  python scanner/scan.py merge    # unește părțile în docs/data/results.json și history.json
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
    "HKT": {"city": "Phuket", "country": "Thailanda"},
    "MRU": {"city": "Port Louis", "country": "Mauritius"},
}

LAST_DEPARTURE = date(2028, 1, 10)
LAST_RETURN = date(2028, 1, 18)
BOOKING_HORIZON_DAYS = 330
STAY_NIGHTS = 7
# zile între plecare și retur: aterizare în aceeași zi, a doua zi sau a treia zi
TRIP_DAYS = (STAY_NIGHTS, STAY_NIGHTS + 1, STAY_NIGHTS + 2)
MAX_DURATION_MIN = 20 * 60
MAX_STOPS = 1
CURRENCY = gf.CURRENCY

WORKERS = 3
KEEP_OPTIONS = 3
TIME_BUDGET_SEC = 5 * 3600  # jobul e oprit de GitHub la 5,5 ore; salvăm ce avem înainte de asta

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"
PARTS_DIR = ROOT / "parts"


def search(origin, dest, dep, trip_days):
    ret = dep + timedelta(days=trip_days)
    r = gf.query([(origin, dest, dep), (dest, origin, ret)], "round-trip", MAX_DURATION_MIN, stay_nights=STAY_NIGHTS, max_stops=MAX_STOPS, return_max_duration_min=MAX_DURATION_MIN, keep=KEEP_OPTIONS)
    return {
        "origin": origin,
        "dest": dest,
        "country": DESTINATIONS[dest]["country"],
        "depart": dep.isoformat(),
        "return": ret.isoformat(),
        "nights": STAY_NIGHTS,
        **r,
    }


def last_bookable():
    """Ultima zi în care un zbor se poate căuta acum."""
    return min(LAST_RETURN, date.today() + timedelta(days=BOOKING_HORIZON_DAYS))


def all_combos():
    d, last = date.today(), last_bookable()
    while d <= LAST_DEPARTURE:
        for origin in ORIGINS:
            for dest in DESTINATIONS:
                for days in TRIP_DAYS:
                    if d + timedelta(days=days) <= last:
                        yield origin, dest, d, days
        d += timedelta(days=1)


def run_shard(shard, total):
    combos = list(all_combos())[shard::total]
    started = datetime.now(timezone.utc)
    print(f"Partea {shard}/{total}: {len(combos)} combinații…", flush=True)

    results = []
    breaker = gf.Breaker()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(search, *c) for c in combos]
        try:
            for i, fut in enumerate(as_completed(futures), 1):
                r = fut.result()
                results.append(r)
                best = r["options"][0]["price"] if r["options"] else "-"
                print(f"[{i}/{len(combos)}] {r['origin']}->{r['dest']} {r['depart']}–{r['return']}: {r['status']} {best} {r.get('error', '')}", flush=True)
                breaker.record(r)
                if (datetime.now(timezone.utc) - started).total_seconds() > TIME_BUDGET_SEC:
                    raise gf.Blocked("timpul alocat s-a terminat")
        except gf.Blocked as e:
            pool.shutdown(wait=False, cancel_futures=True)
            print(f"::warning::Partea {shard} oprită, salvez ce am găsit: {e}", flush=True)

    errors = sum(1 for r in results if r["status"] == "error")
    PARTS_DIR.mkdir(exist_ok=True)
    (PARTS_DIR / f"direct-{shard}.json").write_text(json.dumps({
        "started": started.isoformat(timespec="seconds"),
        "duration_sec": int((datetime.now(timezone.utc) - started).total_seconds()),
        "planned": len(combos),
        "done": len(results),
        "errors": errors,
        "results": [{k: v for k, v in r.items() if k not in ("link", "status", "error")} for r in results if r["options"]],
    }, ensure_ascii=False))
    print(f"Gata: {len(results)} din {len(combos)}, {errors} erori")
    return 0


def merge():
    parts = [json.loads(f.read_text()) for f in PARTS_DIR.glob("direct-*.json")]
    planned = len(list(all_combos()))
    done = sum(p["done"] for p in parts)
    errors = sum(p["errors"] for p in parts)

    # Dacă scanarea a eșuat în mare parte (ex. blocare temporară), păstrăm datele vechi.
    if done - errors < 0.5 * planned:
        print(f"::error::Doar {done - errors} căutări reușite din {planned}, păstrez rezultatele anterioare.")
        return 1

    results = [r for p in parts for r in p["results"]]
    results.sort(key=lambda r: r["options"][0]["price"])

    payload = {
        "scanned_at": min(p["started"] for p in parts),
        "duration_sec": max(p["duration_sec"] for p in parts),
        "currency": CURRENCY,
        "passengers": "2 adulți + 2 copii (3 și 5 ani)",
        "max_duration_h": MAX_DURATION_MIN // 60,
        "stay_nights": STAY_NIGHTS,
        "max_stops": MAX_STOPS,
        "return_checked": True,
        "last_departure": LAST_DEPARTURE.isoformat(),
        "last_return": LAST_RETURN.isoformat(),
        "bookable_until": last_bookable().isoformat(),
        "origins": ORIGINS,
        "destinations": DESTINATIONS,
        "stats": {"total": planned, "searched": done, "with_price": len(results), "errors": errors},
        "results": results,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "results.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

    hist_path = DATA_DIR / "history.json"
    history = json.loads(hist_path.read_text()) if hist_path.exists() else []
    # Prețurile fără retur verificat nu se pot compara cu cele noi.
    history = [h for h in history if h.get("return_checked")]
    entry = {"t": payload["scanned_at"], "return_checked": True, "best": {}}
    for r in results:
        c = r["country"]
        for o in r["options"]:
            if o["bag_transfer"] == "auto" and (c not in entry["best"] or o["price"] < entry["best"][c]):
                entry["best"][c] = o["price"]
    history.append(entry)
    hist_path.write_text(json.dumps(history[-120:], ensure_ascii=False))

    print(f"Gata: {len(results)} cu preț, {errors} erori, {done} din {planned} căutări")
    return 0


if __name__ == "__main__":
    sys.exit(merge() if sys.argv[1] == "merge" else run_shard(int(sys.argv[1]), int(sys.argv[2])))
