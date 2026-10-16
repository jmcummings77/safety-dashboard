"""Check the committed dashboard export has the shape site/index.html expects."""

import json
import re
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent / "site"


@pytest.fixture(scope="module")
def data():
    text = (SITE / "data.js").read_text()
    m = re.fullmatch(r"window\.SAFETY_DATA = (.*);\s*", text, re.S)
    assert m, "data.js must assign window.SAFETY_DATA"
    return json.loads(m.group(1))


def test_index_references_existing_scripts():
    html = (SITE / "index.html").read_text()
    for local in re.findall(r'<script src="([^":]+)"', html):
        assert (SITE / local).exists(), local


def test_rides_export(data):
    rides = data["rides"]
    assert rides["source"]["as_of"]
    assert len(rides["incidents"]) > 500
    required = {"date", "q", "park", "ride", "age", "sex", "desc", "sev", "type", "pre"}
    assert all(required <= r.keys() for r in rides["incidents"])
    assert {r["sev"] for r in rides["incidents"]} <= {"fatal", "serious", "other"}


def test_bridges_export(data):
    b = data["bridges"]
    assert sum(s["total"] for s in b["states"]) > 600_000
    for s in b["states"]:
        assert s["good"] + s["fair"] + s["poor"] <= s["total"]
    assert all(w["state"] in {s["state"] for s in b["states"]} for w in b["worst"])
    assert all(len(p) == 3 for p in b["poor_points"])
