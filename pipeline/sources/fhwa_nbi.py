"""FHWA National Bridge Inventory (NBI), delimited highway-bridge file.

Every US highway bridge over 20 ft, as submitted annually by the states. Each record carries the
most recent routine inspection date, the required inspection interval, and 0-9 condition ratings
for deck / superstructure / substructure / culvert. FHWA derives Good/Fair/Poor from the lowest.
"""

import csv
import datetime as dt

SOURCE = {
    "id": "fhwa_nbi",
    "name": "National Bridge Inventory — Highway Bridges",
    "agency": "Federal Highway Administration",
    "jurisdiction": "US",
    "domain": "bridge",
    "url": "https://www.fhwa.dot.gov/bridge/nbi/ascii2025.cfm",
    "notes": "Annual snapshot submitted by state DOTs. Condition = lowest of deck, superstructure, "
    "substructure and culvert ratings (Poor <= 4). Inspection data is as of submission.",
}
YEAR = 2025
DOWNLOAD = f"https://www.fhwa.dot.gov/bridge/nbi/{YEAR}hwybronefiledel.zip"

STATES = {
    "01": "AL",
    "02": "AK",
    "04": "AZ",
    "05": "AR",
    "06": "CA",
    "08": "CO",
    "09": "CT",
    "10": "DE",
    "11": "DC",
    "12": "FL",
    "13": "GA",
    "15": "HI",
    "16": "ID",
    "17": "IL",
    "18": "IN",
    "19": "IA",
    "20": "KS",
    "21": "KY",
    "22": "LA",
    "23": "ME",
    "24": "MD",
    "25": "MA",
    "26": "MI",
    "27": "MN",
    "28": "MS",
    "29": "MO",
    "30": "MT",
    "31": "NE",
    "32": "NV",
    "33": "NH",
    "34": "NJ",
    "35": "NM",
    "36": "NY",
    "37": "NC",
    "38": "ND",
    "39": "OH",
    "40": "OK",
    "41": "OR",
    "42": "PA",
    "44": "RI",
    "45": "SC",
    "46": "SD",
    "47": "TN",
    "48": "TX",
    "49": "UT",
    "50": "VT",
    "51": "VA",
    "53": "WA",
    "54": "WV",
    "55": "WI",
    "56": "WY",
    "72": "PR",
    "66": "GU",
    "78": "VI",
}
OWNERS = {
    "01": "State DOT",
    "02": "County",
    "03": "Town/Township",
    "04": "City",
    "11": "State Park",
    "25": "Other Local",
    "26": "Private",
    "27": "Railroad",
    "31": "State Toll Authority",
    "32": "Local Toll Authority",
}
COND = {"G": "good", "F": "fair", "P": "poor"}


def _dms(raw, digits):
    """NBI stores lat as DDMMSSss and long as DDDMMSSss."""
    raw = (raw or "").strip()
    if not raw.isdigit() or int(raw) == 0:
        return None
    raw = raw.zfill(digits + 6)
    d, m, s = int(raw[:digits]), int(raw[digits : digits + 2]), int(raw[digits + 2 :]) / 100
    return round(d + m / 60 + s / 3600, 5)


def _inspect_date(raw):
    """Item 90 is MMYY, sometimes with the leading zero dropped ("223" = Feb 2023)."""
    raw = (raw or "").strip().zfill(4)
    if not raw.isdigit():
        return None
    m, y = int(raw[:2]), int(raw[2:])
    if not 1 <= m <= 12:
        return None
    return dt.date(2000 + y if y < 50 else 1900 + y, m, 1)


def _months_between(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month)


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse(path, snapshot=dt.date(YEAR, 6, 1)):
    """Yield one normalized dict per bridge."""
    with open(path, newline="", encoding="latin-1") as fh:
        for r in csv.DictReader(fh, quotechar="'"):
            insp = _inspect_date(r["DATE_OF_INSPECT_090"])
            freq = _int(r["INSPECT_FREQ_MONTHS_091"]) or 24
            age_m = _months_between(insp, snapshot) if insp else None
            lowest = _int(r["LOWEST_RATING"])
            yield {
                "id": f"{r['STATE_CODE_001']}-{r['STRUCTURE_NUMBER_008'].strip()}",
                "state": STATES.get(r["STATE_CODE_001"], r["STATE_CODE_001"]),
                "carries": r["FACILITY_CARRIED_007"].strip(),
                "crosses": r["FEATURES_DESC_006A"].strip(),
                "location": r["LOCATION_009"].strip(),
                "lat": _dms(r["LAT_016"], 2),
                "lon": -_dms(r["LONG_017"], 3) if _dms(r["LONG_017"], 3) else None,
                "owner": OWNERS.get(r["OWNER_022"].zfill(2), "Other"),
                "year_built": _int(r["YEAR_BUILT_027"]),
                "adt": _int(r["ADT_029"]),
                "condition": COND.get(r["BRIDGE_CONDITION"].strip()),
                "lowest_rating": lowest,
                "deck": r["DECK_COND_058"],
                "super": r["SUPERSTRUCTURE_COND_059"],
                "sub": r["SUBSTRUCTURE_COND_060"],
                "culvert": r["CULVERT_COND_062"],
                "posted": r["OPEN_CLOSED_POSTED_041"].strip(),  # A=open, B/P/R=posted, K=closed
                "scour_critical": r["SCOUR_CRITICAL_113"].strip() in {"0", "1", "2", "3"},
                "inspected": insp.isoformat() if insp else None,
                "inspect_freq_months": freq,
                "months_since_inspection": age_m,
                "overdue": age_m is not None and age_m > freq,
                "improvement_cost_k": _int(r["TOTAL_IMP_COST_096"]),
            }
