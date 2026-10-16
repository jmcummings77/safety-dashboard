import datetime as dt
from pathlib import Path

import pytest

from sources import fhwa_nbi

FIXTURE = Path(__file__).parent / "fixtures" / "nbi_sample.csv"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("223", dt.date(2023, 2, 1)),
        ("1124", dt.date(2024, 11, 1)),
        ("0899", dt.date(1999, 8, 1)),
        ("1324", None),
        ("", None),
        ("ab12", None),
    ],
)
def test_inspect_date(raw, expected):
    assert fhwa_nbi._inspect_date(raw) == expected


def test_dms_latitude_and_longitude():
    assert fhwa_nbi._dms("31061094", 2) == pytest.approx(31.10304, abs=1e-5)
    assert fhwa_nbi._dms("087341348", 3) == pytest.approx(87.57041, abs=1e-5)
    assert fhwa_nbi._dms("00000000", 2) is None


def test_parse_fixture():
    rows = list(fhwa_nbi.parse(FIXTURE, snapshot=dt.date(2025, 1, 1)))
    assert [r["condition"] for r in rows] == ["good", "poor", "poor"]
    good, poor, closed = rows
    assert good["state"] == "AL"
    assert good["lon"] < 0
    assert poor["lowest_rating"] <= 4
    assert closed["posted"] == "K"
    assert closed["months_since_inspection"] > closed["inspect_freq_months"]
    assert closed["overdue"] is True
    assert good["overdue"] is False
