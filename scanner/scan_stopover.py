"""Combinații cu bilete separate și oprire de 1–3 zile într-un oraș-hub.

Exemplu: Timișoara → Milano cu Wizz Air, 1–2 nopți în Milano, apoi Milano → Maldive
dus-întors, iar la întoarcere încă 1–2 nopți în Milano și zbor separat spre casă.

Se caută separat, pe Google Flights:
  1. zborurile de poziționare dus:   casă → hub   (o singură direcție)
  2. zborurile lungi dus-întors:     hub → destinație exotică
  3. zborurile de poziționare întors: hub → casă  (o singură direcție)
apoi se combină toate variantele și se păstrează cele mai ieftine.

Biletele sunt separate: fără transfer automat de bagaje și fără protecție dacă
un zbor întârzie — de aceea fiecare combinație are cel puțin o noapte în hub.

Rezultatul se scrie în docs/data/stopovers.json.
"""

import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import gf
from scan import DATA_DIR, DESTINATIONS, FIRST_DEPARTURE, LAST_DEPARTURE, ORIGINS, STAY_NIGHTS, TRIP_DAYS

HUBS = {
    "MIL": "Milano",
    "ROM": "Roma",
    "MAD": "Madrid",
    "BCN": "Barcelona",
    "LON": "Londra",
    "PAR": "Paris",
    "MUC": "München",
    "VIE": "Viena",
    "ATH": "Atena",
    "IST": "Istanbul",
    "DXB": "Dubai",
    "AUH": "Abu Dhabi",
    "DOH": "Doha",
}

# nopți în hub la plecare (zborul spre hub e scurt, ajungi în aceeași zi)
STOP_OUT_DAYS = (1, 2)
# zile între plecarea din destinația exotică și zborul spre casă;
# zborurile lungi de noapte aterizează adesea a doua zi, deci 2–3 zile = 1–2 nopți în hub
STOP_RET_DAYS = (2, 3)

MAX_POSITIONING_MIN = 12 * 60
MAX_LONGHAUL_MIN = 30 * 60

# Prețurile low-cost de pe Google Flights nu includ bagajul de cală.
LOW_COST = ("Wizz", "Ryanair", "easyJet", "Pegasus", "flydubai", "Air Arabia", "Vueling",
            "Transavia", "Eurowings", "AJet", "Volotea", "SkyUp", "HiSky")
BAG_FEE_PER_LEG = 100  # estimare: 2 bagaje de cală de 20 kg pe un zbor low-cost

KEEP_PER_GROUP = 25  # cele mai bune combinații pentru fiecare (oraș de plecare, țară)
WORKERS = 3


def is_low_cost(airlines):
    names = [a.strip() for a in (airlines or "").split(",") if a.strip()]
    return bool(names) and all(any(lc.lower() in n.lower() for lc in LOW_COST) for n in names)


def leg(r, **extra):
    o = r["options"][0]
    low = is_low_cost(o["airlines"])
    return {**extra, **o, "link": r["link"], "low_cost": low, "bag_fee": BAG_FEE_PER_LEG if low else 0}


def tasks():
    lh_first = FIRST_DEPARTURE + timedelta(days=min(STOP_OUT_DAYS))
    lh_last = LAST_DEPARTURE + timedelta(days=max(STOP_OUT_DAYS))
    lh_dates = [lh_first + timedelta(days=i) for i in range((lh_last - lh_first).days + 1)]
    ret_dates = sorted({d + timedelta(days=n + s) for d in lh_dates for n in TRIP_DAYS for s in STOP_RET_DAYS})
    home_dates = [FIRST_DEPARTURE + timedelta(days=i) for i in range((LAST_DEPARTURE - FIRST_DEPARTURE).days + 1)]

    for h in HUBS:
        for o in ORIGINS:
            for d in home_dates:
                yield ("out", o, h, d, None)
            for d in ret_dates:
                yield ("ret", h, o, d, None)
        for dest in DESTINATIONS:
            for d in lh_dates:
                for n in TRIP_DAYS:
                    yield ("lh", h, dest, d, n)


def run(task):
    kind, a, b, d, n = task
    if kind == "lh":
        r = gf.query([(a, b, d), (b, a, d + timedelta(days=n))], "round-trip", MAX_LONGHAUL_MIN, keep=1, stay_nights=STAY_NIGHTS)
    else:
        r = gf.query([(a, b, d)], "one-way", MAX_POSITIONING_MIN, keep=1)
    return task, r


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    all_tasks = list(tasks())[:limit]
    started = datetime.now(timezone.utc)
    print(f"Scanez {len(all_tasks)} zboruri separate…", flush=True)

    out, ret, lh = {}, {}, {}
    errors = 0
    breaker = gf.Breaker()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(run, t) for t in all_tasks]
        for i, fut in enumerate(as_completed(futures), 1):
            (kind, a, b, d, n), r = fut.result()
            errors += r["status"] == "error"
            try:
                breaker.record(r)
            except gf.Blocked as e:
                pool.shutdown(wait=False, cancel_futures=True)
                print(f"::error::Scanare oprită, datele vechi rămân: {e}", flush=True)
                return 1
            if i % 100 == 0:
                print(f"[{i}/{len(all_tasks)}] erori: {errors}", flush=True)
            if not r["options"]:
                continue
            if kind == "out":
                out[(a, b, d)] = leg(r, origin=a, to=b, date=d.isoformat())
            elif kind == "ret":
                ret[(a, b, d)] = leg(r, origin=a, to=b, date=d.isoformat())
            else:
                lh[(a, b, d, n)] = leg(r, origin=a, to=b, date=d.isoformat(),
                                       return_date=(d + timedelta(days=n)).isoformat(),
                                       nights=STAY_NIGHTS, price_level=r.get("price_level"))

    # Combinăm: casă → hub (+1–2 nopți) → destinație (7 nopți de la aterizare) → hub (+1–2 nopți) → casă
    groups = defaultdict(list)
    for (h, dest, lh_dep, n), long_leg in lh.items():
        lh_ret = lh_dep + timedelta(days=n)
        for o in ORIGINS:
            for s_out in STOP_OUT_DAYS:
                first = out.get((o, h, lh_dep - timedelta(days=s_out)))
                if not first:
                    continue
                for s_ret in STOP_RET_DAYS:
                    last = ret.get((h, o, lh_ret + timedelta(days=s_ret)))
                    if not last:
                        continue
                    legs = [first, long_leg, last]
                    tickets = sum(x["price"] for x in legs)
                    bags = sum(x["bag_fee"] for x in legs)
                    groups[(o, DESTINATIONS[dest]["country"])].append({
                        "origin": o,
                        "hub": h,
                        "dest": dest,
                        "country": DESTINATIONS[dest]["country"],
                        "depart": first["date"],
                        "home": last["date"],
                        "nights": STAY_NIGHTS,
                        "stop_out": s_out,
                        "stop_ret": s_ret,
                        "tickets": tickets,
                        "bags": bags,
                        "total": tickets + bags,
                        "legs": legs,
                    })

    # Păstrăm cele mai bune combinații pe (oraș de plecare, țară), plus cele mai bune 2
    # pentru fiecare (oraș de plecare, hub, destinație), ca tabelul de hub-uri să fie complet.
    combos, kept = [], set()
    for items in groups.values():
        items.sort(key=lambda c: c["total"])
        per_route = defaultdict(int)
        for i, c in enumerate(items):
            key = (c["hub"], c["dest"])
            if i < KEEP_PER_GROUP or per_route[key] < 2:
                if id(c) not in kept:
                    kept.add(id(c))
                    combos.append(c)
            per_route[key] += 1
    combos.sort(key=lambda c: c["total"])

    out_path = DATA_DIR / "stopovers.json"
    if len(all_tasks) > 50 and errors > 0.8 * len(all_tasks) and out_path.exists():
        print(f"Prea multe erori ({errors}/{len(all_tasks)}), păstrez rezultatele anterioare.")
        return 1

    payload = {
        "scanned_at": started.isoformat(timespec="seconds"),
        "duration_sec": int((datetime.now(timezone.utc) - started).total_seconds()),
        "currency": gf.CURRENCY,
        "hubs": HUBS,
        "bag_fee_per_leg": BAG_FEE_PER_LEG,
        "stay_nights": STAY_NIGHTS,
        "stats": {
            "searches": len(all_tasks),
            "errors": errors,
            "positioning_found": len(out) + len(ret),
            "longhaul_found": len(lh),
            "combinations": sum(len(v) for v in groups.values()),
        },
        "combos": combos,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    print(f"Gata: {payload['stats']} în {payload['duration_sec']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
