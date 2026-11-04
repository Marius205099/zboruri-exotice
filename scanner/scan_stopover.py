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

Scanarea se împarte pe joburi paralele, ca în scan.py:
  python scanner/scan_stopover.py 0 20     # partea 0 din 20, scrisă în parts/
  python scanner/scan_stopover.py merge    # combină zborurile în docs/data/stopovers.json
"""

import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone

import gf
from scan import (DATA_DIR, DESTINATIONS, LAST_DEPARTURE, LAST_RETURN, MAX_STOPS, ORIGINS, PARTS_DIR, STAY_NIGHTS,
                  TIME_BUDGET_SEC, TRIP_DAYS, last_bookable)

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
# nopți în hub la întoarcere, numărate de la aterizarea zborului de retur
STOP_RET_NIGHTS = (1, 2)
# zile cu care returul poate ateriza după data plecării (zboruri fără limită de durată)
MAX_RETURN_DAYS = 2

MAX_POSITIONING_MIN = 12 * 60
LONGHAUL_TRIES = 3  # câte zboruri dus încercăm până găsim un retur cu cel mult o escală

BAG_FEE_PER_LEG = 100  # estimare: 2 bagaje de cală de 20 kg pe un zbor low-cost

KEEP_PER_MONTH = 5  # cele mai bune combinații pe lună, pentru fiecare (oraș de plecare, țară)
WORKERS = 3


def is_low_cost(airlines):
    names = [a.strip() for a in (airlines or "").split(",") if a.strip()]
    return bool(names) and all(any(lc.lower() in n.lower() for lc in gf.LOW_COST) for n in names)


def leg(r, **extra):
    o = r["options"][0]
    names = [o["airlines"]] + ([o["return_flight"]["airlines"]] if "return_flight" in o else [])
    fee = BAG_FEE_PER_LEG * sum(is_low_cost(n) for n in names)
    return {**extra, "link": r["link"], **o, "low_cost": fee > 0, "bag_fee": fee}


def tasks():
    today, last = date.today(), last_bookable()
    longest = max(STOP_RET_NIGHTS)
    days = lambda first, end: [first + timedelta(days=i) for i in range((end - first).days + 1)]  # noqa: E731
    lh_first = today + timedelta(days=min(STOP_OUT_DAYS))
    lh_dates = days(lh_first, LAST_DEPARTURE + timedelta(days=max(STOP_OUT_DAYS)))
    ret_dates = days(lh_first + timedelta(days=min(TRIP_DAYS) + min(STOP_RET_NIGHTS)), last)
    home_dates = days(today, min(LAST_DEPARTURE, last))

    for h in HUBS:
        for o in ORIGINS:
            for d in home_dates:
                yield ("out", o, h, d, None)
            for d in ret_dates:
                if d <= lh_dates[-1] + timedelta(days=max(TRIP_DAYS) + MAX_RETURN_DAYS + longest):
                    yield ("ret", h, o, d, None)
        for dest in DESTINATIONS:
            for d in lh_dates:
                for n in TRIP_DAYS:
                    # după retur rămâne cel puțin o noapte în hub înainte de zborul spre casă
                    if d + timedelta(days=n + min(STOP_RET_NIGHTS)) <= last:
                        yield ("lh", h, dest, d, n)


def run(task):
    kind, a, b, d, n = task
    if kind == "lh":
        r = gf.query([(a, b, d), (b, a, d + timedelta(days=n))], "round-trip", keep=1, stay_nights=STAY_NIGHTS, max_stops=MAX_STOPS, tries=LONGHAUL_TRIES)
    else:
        r = gf.query([(a, b, d)], "one-way", MAX_POSITIONING_MIN, keep=1, max_stops=MAX_STOPS)
    return task, r


def run_shard(shard, total):
    all_tasks = list(tasks())[shard::total]
    started = datetime.now(timezone.utc)
    print(f"Partea {shard}/{total}: {len(all_tasks)} zboruri separate…", flush=True)

    found = []
    done = errors = 0
    breaker = gf.Breaker()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(run, t) for t in all_tasks]
        try:
            for fut in as_completed(futures):
                (kind, a, b, d, n), r = fut.result()
                done += 1
                errors += r["status"] == "error"
                breaker.record(r)
                if (datetime.now(timezone.utc) - started).total_seconds() > TIME_BUDGET_SEC:
                    raise gf.Blocked("timpul alocat s-a terminat")
                if done % 100 == 0:
                    print(f"[{done}/{len(all_tasks)}] erori: {errors}", flush=True)
                if not r["options"]:
                    continue
                if kind == "lh":
                    item = leg(r, origin=a, to=b, date=d.isoformat(),
                               return_date=(d + timedelta(days=n)).isoformat(),
                               nights=STAY_NIGHTS, price_level=r.get("price_level"))
                else:
                    item = leg(r, origin=a, to=b, date=d.isoformat())
                found.append({"kind": kind, "n": n, "leg": item})
        except gf.Blocked as e:
            pool.shutdown(wait=False, cancel_futures=True)
            print(f"::warning::Partea {shard} oprită, salvez ce am găsit: {e}", flush=True)

    PARTS_DIR.mkdir(exist_ok=True)
    (PARTS_DIR / f"stopover-{shard}.json").write_text(json.dumps({
        "started": started.isoformat(timespec="seconds"),
        "duration_sec": int((datetime.now(timezone.utc) - started).total_seconds()),
        "planned": len(all_tasks),
        "done": done,
        "errors": errors,
        "found": found,
    }, ensure_ascii=False))
    print(f"Gata: {done} din {len(all_tasks)}, {errors} erori, {len(found)} zboruri")
    return 0


def merge():
    parts = [json.loads(f.read_text()) for f in PARTS_DIR.glob("stopover-*.json")]
    planned = len(list(tasks()))
    done = sum(p["done"] for p in parts)
    errors = sum(p["errors"] for p in parts)
    if done - errors < 0.5 * planned:
        print(f"::error::Doar {done - errors} căutări reușite din {planned}, păstrez rezultatele anterioare.")
        return 1

    out, ret, lh = {}, {}, {}
    for p in parts:
        for f in p["found"]:
            x, d = f["leg"], date.fromisoformat(f["leg"]["date"])
            if f["kind"] == "out":
                out[(x["origin"], x["to"], d)] = x
            elif f["kind"] == "ret":
                ret[(x["origin"], x["to"], d)] = x
            else:
                lh[(x["origin"], x["to"], d, f["n"])] = x

    # Combinăm: casă → hub (+1–2 nopți) → destinație (7 nopți de la aterizare) → hub (+1–2 nopți) → casă
    groups = defaultdict(list)
    for (h, dest, lh_dep, n), long_leg in lh.items():
        lands = date.fromisoformat(long_leg["return_flight"]["arrival_date"])
        for o in ORIGINS:
            for s_out in STOP_OUT_DAYS:
                first = out.get((o, h, lh_dep - timedelta(days=s_out)))
                if not first or date.fromisoformat(first["arrival_date"]) > lh_dep:
                    continue
                for s_ret in STOP_RET_NIGHTS:
                    last = ret.get((h, o, lands + timedelta(days=s_ret)))
                    if not last or date.fromisoformat(last["date"]) > LAST_RETURN:
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

    # Păstrăm cele mai bune combinații pe lună pentru fiecare (oraș de plecare, țară), plus cele
    # mai bune 2 pentru fiecare (oraș de plecare, hub, destinație), ca tabelul de hub-uri să fie complet.
    combos = []
    for items in groups.values():
        items.sort(key=lambda c: c["total"])
        per_route, per_month = defaultdict(int), defaultdict(int)
        for c in items:
            route, month = (c["hub"], c["dest"]), c["depart"][:7]
            if per_month[month] < KEEP_PER_MONTH or per_route[route] < 2:
                combos.append(c)
            per_month[month] += 1
            per_route[route] += 1
    combos.sort(key=lambda c: c["total"])

    payload = {
        "scanned_at": min(p["started"] for p in parts),
        "duration_sec": max(p["duration_sec"] for p in parts),
        "currency": gf.CURRENCY,
        "hubs": HUBS,
        "bag_fee_per_leg": BAG_FEE_PER_LEG,
        "stay_nights": STAY_NIGHTS,
        "max_stops": MAX_STOPS,
        "return_checked": True,
        "stats": {
            "searches": planned,
            "searched": done,
            "errors": errors,
            "positioning_found": len(out) + len(ret),
            "longhaul_found": len(lh),
            "combinations": sum(len(v) for v in groups.values()),
        },
        "combos": combos,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "stopovers.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    print(f"Gata: {payload['stats']}, {len(combos)} combinații păstrate")
    return 0


if __name__ == "__main__":
    sys.exit(merge() if sys.argv[1] == "merge" else run_shard(int(sys.argv[1]), int(sys.argv[2])))
