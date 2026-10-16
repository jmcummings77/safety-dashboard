"""Florida FDACS "MOU Exempt Facilities Report".

Florida's largest theme parks (Disney, Universal, SeaWorld, Busch Gardens, LEGOLAND) are exempt
from state ride inspections because they employ their own full-time inspectors. In exchange they
must report any ride-related injury/illness that leads to 24h+ hospitalization. FDACS publishes
those self-reports quarterly as one cumulative PDF going back to 2001.

These are incident reports, not maintenance records: they say what happened to a guest, not why.
"""

import contextlib
import datetime as dt
import re

import pdfplumber

SOURCE = {
    "id": "fl_fdacs_exempt",
    "name": "MOU Exempt Facilities Report",
    "agency": "Florida Dept. of Agriculture and Consumer Services",
    "jurisdiction": "US-FL",
    "domain": "amusement_ride",
    "url": "https://ccmedia.fdacs.gov/content/download/81386/file/exempt-facilities-report.pdf",
    "notes": "Self-reported by parks; covers injuries/illnesses with 24h+ hospitalization. "
    "Does not establish cause or fault; FDACS receives no follow-up on guest condition.",
}

PARKS = [
    (r"Sea\s*World", "SeaWorld Orlando"),
    (r"Busch Gardens", "Busch Gardens Tampa Bay"),
    (r"Disney(?: World|/MGM)?", "Walt Disney World"),
    (r"Universal", "Universal Orlando"),
    (r"Legoland", "LEGOLAND Florida"),
    (r"Wet.?n?.?Wild", "Wet 'n Wild Orlando"),
]
PARK_RE = re.compile(r"^(" + "|".join(p for p, _ in PARKS) + r")\s*:?\s*(.*)$", re.I)
QUARTER_RE = re.compile(r"^(\d)(?:st|nd|rd|th) Quarter (\d{4})")
ENTRY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2,4}),?\s+(.*)$")
AGE_RE = re.compile(r"(\d{1,3})(?:\s*,)?\s*(?:yo|y/o|-?\s*year[- ]old)\s*(male|female|m|f|patron|guest)?\b", re.I)
BOILERPLATE = ("The following report", "of the incident", "condition.", "MOU Exempt", "Updated:")
# Older entries prefix the attraction with the gate it's in ("Epcot, Mission: SPACE").
SUBPARK_RE = re.compile(
    r"^(Magic Kingdom|Epcot|MGM(?: Studios)?|Animal Kingdom|Typhoon Lagoon(?: Water Park)?|"
    r"Blizzard Beach|Disney.s Blizzard Beach|Isle of Adv\.?|USF|Orlando|Adventure Island|Wet.n Wild)\s*,\s*",
    re.I,
)

FATAL = re.compile(r"passed away|died|fatalit|death|deceased|expired", re.I)
SERIOUS = re.compile(
    r"cardiac|heart attack|stroke|seizure|fractur|\bfx\b|broken|unconscious|consciousness|"
    r"unresponsive|paraly|amputat|crush|spin(?:e|al)|concussion|aneurysm|embolism",
    re.I,
)
MEDICAL = re.compile(
    r"chest|cardiac|heart|seizure|stroke|nause|vomit|dizz|syncope|faint|ill\b|breath|anxiety|"
    r"asthma|hypertension|consciousness|unresponsive|vertigo|aneurysm|diabet|motion sick|"
    r"abdominal|headache|head pain|numb|palpitat|blood pressure|claustroph|rapid heart|memory",
    re.I,
)
PRE_EXISTING = re.compile(r"pre-?\s?existing|history of|prior", re.I)


def attraction_key(name):
    """Collapse spelling variants ("Harry Potter & the...", "Mission: SPACE", "Space Mtn.")."""
    k = name.lower().replace("&", " and ").replace("’", "'")
    k = re.sub(r"\bmtn\b\.?", "mountain", k)
    k = re.sub(r"\(sic\)|\bride\b|^the\s+", " ", k)
    return re.sub(r"[^a-z0-9]+", "", k)


def _park(raw):
    for pat, name in PARKS:
        if re.fullmatch(pat, raw.strip(), re.I):
            return name
    return raw.strip()


def _date(m, d, y):
    y = int(y)
    if y < 100:
        y += 2000
    try:
        return dt.date(y, int(m), int(d))
    except ValueError:
        return None


def _parse_entry(park, quarter, text):
    m = ENTRY_RE.match(text)
    date = _date(*m.groups()[:3]) if m else None
    body = m.group(4) if m else text
    age = sex = None
    attraction, desc = None, body
    a = AGE_RE.search(body)
    if a:
        age = int(a.group(1))
        g = (a.group(2) or "").lower()
        sex = "F" if g.startswith("f") else "M" if g.startswith("m") else None
        attraction = re.sub(r"(?:,\s*|\s+)an?$", "", body[: a.start()].strip(" ,;")).strip(" ,;")
        desc = (body[a.end() :]).strip(" ,;.")
    if attraction:
        attraction = SUBPARK_RE.sub("", attraction).strip(' ,"“”')
        # Pre-2005 entries sometimes read "<gate>, <complaint>, <age>, <ride>" -- swap them back.
        if desc and "," not in desc and len(desc) < 40 and (MEDICAL.search(attraction) or SERIOUS.search(attraction)):
            attraction, desc = desc, attraction
    sev = "fatal" if FATAL.search(body) else "serious" if SERIOUS.search(body) else "other"
    return {
        "date": date.isoformat() if date else None,
        "quarter": f"{quarter[1]}-Q{quarter[0]}",
        "park": park,
        "attraction": attraction or None,
        "age": age,
        "sex": sex,
        "description": desc or body,
        "raw": text,
        "severity": sev,
        "type": "medical" if MEDICAL.search(body) else "injury",
        "pre_existing": bool(PRE_EXISTING.search(body)),
    }


def parse(pdf_path):
    """Return (as_of date, [incident dicts]) for the report PDF."""
    with pdfplumber.open(pdf_path) as pdf:
        lines = "\n".join(p.extract_text() or "" for p in pdf.pages).splitlines()
    return parse_lines(lines)


def parse_lines(lines):
    """Parse the report's extracted text, one PDF line per item."""
    as_of = None
    quarter = park = None
    entries, current = [], None

    def flush():
        nonlocal current
        if current:
            entries.append(_parse_entry(*current))
        current = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("Updated:"):
            with contextlib.suppress(ValueError):
                as_of = dt.datetime.strptime(line[8:].strip(), "%B %d, %Y").date().isoformat()
        if line.startswith(BOILERPLATE):
            continue
        q = QUARTER_RE.match(line)
        if q:
            flush()
            quarter, park = (int(q.group(1)), int(q.group(2))), None
            continue
        if quarter is None:
            continue
        p = PARK_RE.match(line)
        if p:
            flush()
            park = _park(p.group(1))
            line = p.group(2).strip()
            if not line or re.match(r"none", line, re.I):
                continue
        if ENTRY_RE.match(line):
            flush()
            current = (park, quarter, line)
        elif current:
            current = (current[0], current[1], current[2] + " " + line)
    flush()
    return as_of, entries


def to_records(entries):
    """Map parsed entries onto the shared asset/event schema."""
    assets, events = {}, []
    for e in entries:
        asset_id = None
        if e["attraction"]:
            key = attraction_key(e["attraction"])
            asset_id = f"{SOURCE['id']}:{e['park']}:{key}"
            assets.setdefault(
                asset_id,
                {
                    "id": asset_id,
                    "name": e["attraction"],
                    "operator": e["park"],
                    "region": "FL",
                },
            )
        events.append(
            {
                "asset_id": asset_id,
                "kind": "incident",
                "date": e["date"],
                "severity": e["severity"],
                "summary": e["description"],
                "attrs": e,
            }
        )
    return list(assets.values()), events
