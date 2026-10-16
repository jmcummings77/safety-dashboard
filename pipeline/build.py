"""Fetch every source, load it into data/safety.db, and export site/data.js for the dashboard.

python pipeline/build.py            # use cached raw files when present
python pipeline/build.py --refresh  # re-download everything
"""

import argparse
import collections
import datetime as dt
import json
import sqlite3
import statistics
import sys
import urllib.request
import zipfile
from pathlib import Path

from sources import fhwa_nbi, fl_fdacs

ROOT = Path(__file__).resolve().parent.parent
RAW, DATA, SITE = ROOT / "raw", ROOT / "data", ROOT / "site"
US_ATLAS = "https://cdn.jsdelivr.net/npm/us-atlas@3.0.1/states-albers-10m.json"
UA = {"User-Agent": "Mozilla/5.0 (public-safety-dashboard)"}

# NBI submissions reflect each state's inventory as of roughly the end of the prior year.
NBI_SNAPSHOT = dt.date(fhwa_nbi.YEAR, 1, 1)
# NBIS allows some scheduling tolerance, so only flag inspections well past their interval.
OVERDUE_GRACE_MONTHS = 3


def fetch(url, dest, refresh):
    if dest.exists() and not refresh:
        return dest
    print(f"  downloading {url}")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as fh:
        fh.write(r.read())
    return dest


def init_db():
    DATA.mkdir(exist_ok=True)
    db_path = DATA / "safety.db"
    db_path.unlink(missing_ok=True)
    db = sqlite3.connect(db_path)
    db.executescript((ROOT / "pipeline" / "schema.sql").read_text())
    return db


def add_source(db, src, as_of):
    db.execute(
        "INSERT INTO sources VALUES (:id,:name,:agency,:jurisdiction,:domain,:url,:fetched_at,:as_of,:notes)",
        {**src, "fetched_at": dt.datetime.now().isoformat(timespec="seconds"), "as_of": as_of},
    )


# ---------------------------------------------------------------- Florida theme parks


def build_florida(db, refresh):
    print("Florida FDACS exempt facilities report")
    pdf = fetch(fl_fdacs.SOURCE["url"], RAW / "fl_fdacs_exempt.pdf", refresh)
    as_of, entries = fl_fdacs.parse(pdf)
    assets, events = fl_fdacs.to_records(entries)
    add_source(db, fl_fdacs.SOURCE, as_of)
    db.executemany(
        "INSERT INTO assets (id, source_id, domain, name, operator, region) VALUES (?,?,?,?,?,?)",
        [(a["id"], fl_fdacs.SOURCE["id"], "amusement_ride", a["name"], a["operator"], a["region"]) for a in assets],
    )
    db.executemany(
        "INSERT INTO events (source_id, asset_id, kind, date, severity, summary, attrs) VALUES (?,?,?,?,?,?,?)",
        [
            (
                fl_fdacs.SOURCE["id"],
                e["asset_id"],
                e["kind"],
                e["date"],
                e["severity"],
                e["summary"],
                json.dumps(e["attrs"]),
            )
            for e in events
        ],
    )
    print(f"  {len(entries)} incidents, {len(assets)} attractions, as of {as_of}")

    # Use the most common spelling as each attraction's display name.
    spellings = collections.defaultdict(collections.Counter)
    for e in entries:
        if e["attraction"]:
            spellings[(e["park"], fl_fdacs.attraction_key(e["attraction"]))][e["attraction"]] += 1
    display = {k: c.most_common(1)[0][0] for k, c in spellings.items()}

    incidents = []
    for e in sorted(entries, key=lambda e: e["date"] or "", reverse=True):
        key = (e["park"], fl_fdacs.attraction_key(e["attraction"])) if e["attraction"] else None
        incidents.append(
            {
                "date": e["date"],
                "q": e["quarter"],
                "park": e["park"],
                "ride": display.get(key, e["attraction"]),
                "age": e["age"],
                "sex": e["sex"],
                "desc": e["description"],
                "sev": e["severity"],
                "type": e["type"],
                "pre": e["pre_existing"],
            }
        )
    return {"source": {**fl_fdacs.SOURCE, "as_of": as_of}, "incidents": incidents}


# ---------------------------------------------------------------- Bridges

FIPS = {abbr: code for code, abbr in fhwa_nbi.STATES.items()}


def build_bridges(db, refresh):
    print(f"FHWA National Bridge Inventory {fhwa_nbi.YEAR}")
    zpath = fetch(fhwa_nbi.DOWNLOAD, RAW / f"fhwa_nbi_{fhwa_nbi.YEAR}.zip", refresh)
    with zipfile.ZipFile(zpath) as z:
        name = z.namelist()[0]
        txt = RAW / name
        if not txt.exists() or refresh:
            z.extract(name, RAW)
    add_source(db, fhwa_nbi.SOURCE, NBI_SNAPSHOT.isoformat())

    by_state = collections.defaultdict(list)
    asset_rows, event_rows = [], []
    sid = fhwa_nbi.SOURCE["id"]
    for b in fhwa_nbi.parse(txt, snapshot=NBI_SNAPSHOT):
        b["overdue"] = (b["months_since_inspection"] or 0) > b["inspect_freq_months"] + OVERDUE_GRACE_MONTHS
        by_state[b["state"]].append(b)
        aid = f"{sid}:{b['id']}"
        asset_rows.append(
            (
                aid,
                sid,
                "bridge",
                f"{b['carries']} over {b['crosses']}",
                b["owner"],
                b["state"],
                b["lat"],
                b["lon"],
                json.dumps(b),
            )
        )
        event_rows.append((sid, aid, "inspection", b["inspected"], b["condition"], None, None))
    # A handful of structure numbers repeat within a state; keep the first record.
    db.executemany("INSERT OR IGNORE INTO assets VALUES (?,?,?,?,?,?,?,?,?)", asset_rows)
    db.executemany(
        "INSERT INTO events (source_id, asset_id, kind, date, severity, summary, attrs) VALUES (?,?,?,?,?,?,?)",
        event_rows,
    )
    print(f"  {len(asset_rows)} bridges")

    states, worst, points = [], [], []
    for st, bs in sorted(by_state.items()):
        cond = collections.Counter(b["condition"] for b in bs)
        years = [b["year_built"] for b in bs if b["year_built"] and b["year_built"] > 1700]
        poor = [b for b in bs if b["condition"] == "poor"]
        states.append(
            {
                "state": st,
                "fips": FIPS.get(st),
                "total": len(bs),
                "good": cond["good"],
                "fair": cond["fair"],
                "poor": cond["poor"],
                "closed": sum(b["posted"] == "K" for b in bs),
                "posted": sum(b["posted"] in {"B", "P", "R"} for b in bs),
                "overdue": sum(b["overdue"] for b in bs),
                "scour": sum(b["scour_critical"] for b in bs),
                "median_age": NBI_SNAPSHOT.year - int(statistics.median(years)) if years else None,
                "poor_daily_crossings": sum(b["adt"] or 0 for b in poor),
            }
        )
        # The poor bridges that carry the most traffic in each state.
        for b in sorted(poor, key=lambda b: b["adt"] or 0, reverse=True)[:40]:
            worst.append(
                {
                    k: b[k]
                    for k in (
                        "id",
                        "state",
                        "carries",
                        "crosses",
                        "location",
                        "owner",
                        "year_built",
                        "adt",
                        "lowest_rating",
                        "deck",
                        "super",
                        "sub",
                        "culvert",
                        "posted",
                        "inspected",
                        "overdue",
                        "lat",
                        "lon",
                    )
                }
            )
        points += [[b["lon"], b["lat"], b["adt"] or 0] for b in poor if b["lat"] and b["lon"]]
    return {
        "source": {**fhwa_nbi.SOURCE, "as_of": NBI_SNAPSHOT.isoformat(), "overdue_grace_months": OVERDUE_GRACE_MONTHS},
        "states": states,
        "worst": worst,
        "poor_points": [[round(x, 3), round(y, 3), a] for x, y, a in points],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download source files")
    args = ap.parse_args()
    RAW.mkdir(exist_ok=True)
    db = init_db()
    out = {
        "built_at": dt.datetime.now().isoformat(timespec="seconds"),
        "rides": build_florida(db, args.refresh),
        "bridges": build_bridges(db, args.refresh),
    }
    db.commit()
    SITE.mkdir(exist_ok=True)
    (SITE / "data.js").write_text("window.SAFETY_DATA = " + json.dumps(out, separators=(",", ":")) + ";\n")
    atlas = fetch(US_ATLAS, RAW / "states-albers-10m.json", args.refresh)
    (SITE / "us-states.js").write_text("window.US_STATES = " + atlas.read_text() + ";\n")
    print(f"wrote {SITE / 'data.js'} ({(SITE / 'data.js').stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    sys.exit(main())
