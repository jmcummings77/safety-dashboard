from sources import fl_fdacs

# Excerpts of the report's extracted text, covering the modern format, the pre-2005 format,
# multi-line entries, page boilerplate mid-entry, and parks with nothing to report.
SAMPLE = """\
The following report is a compilation of data collected from the exempt facilities and reflects only the information reported at the time
of the incident. Due to privacy-related concerns, the Department does not receive updates to initial assessments of a patron's
condition.
MOU Exempt Facilities Report
Updated: October 15, 2026
3rd Quarter 2026 (July - September 2026)
Sea World: None Reported
Disney World: 7/11/26 Humunga Kowabunga, 25 yof, guest injured right leg while on the
attraction
9/25/26 Pirates of the Caribbean, 45 yom, guest had a seizure after exiting the
attraction
Universal: 7/6/26 Fast & Furious Supercharged, 61 yom, abdominal pain (pre-existing
condition)
Legoland None Reported
2nd Quarter 2026 (April - June 2026)
Disney World: 4/24/26 It's A Small World, 54 yom, guest with pre-existing condition
experienced a cardiac emergency on the attraction, was transported to the
hospital and later passed away
1st Quarter 2004 (January - March, 2004)
Disney: 03/24/04 Epcot, Chest Pains, 59 year old female, Mission: Space
Universal: 01/08/04, Fractured Toe, 12 year old male, Men In Black
""".splitlines()


def parsed():
    return fl_fdacs.parse_lines(SAMPLE)


def test_reads_update_date():
    as_of, _ = parsed()
    assert as_of == "2026-10-15"


def test_counts_entries_and_skips_none_reported():
    _, entries = parsed()
    assert len(entries) == 6
    assert {e["park"] for e in entries} == {"Walt Disney World", "Universal Orlando"}


def test_modern_entry_fields():
    _, entries = parsed()
    e = entries[0]
    assert e["date"] == "2026-07-11"
    assert e["quarter"] == "2026-Q3"
    assert e["attraction"] == "Humunga Kowabunga"
    assert (e["age"], e["sex"]) == (25, "F")
    assert e["description"] == "guest injured right leg while on the attraction"
    assert e["type"] == "injury"


def test_multiline_entry_is_joined_and_classified():
    _, entries = parsed()
    small_world = next(e for e in entries if e["attraction"] == "It's A Small World")
    assert small_world["severity"] == "fatal"
    assert small_world["pre_existing"] is True
    assert small_world["type"] == "medical"
    assert "later passed away" in small_world["description"]


def test_seizure_is_serious():
    _, entries = parsed()
    pirates = next(e for e in entries if e["attraction"] == "Pirates of the Caribbean")
    assert pirates["severity"] == "serious"


def test_old_format_puts_ride_back_in_attraction():
    _, entries = parsed()
    epcot = next(e for e in entries if e["date"] == "2004-03-24")
    assert epcot["attraction"] == "Mission: Space"
    assert epcot["description"] == "Chest Pains"
    assert (epcot["age"], epcot["sex"]) == (59, "F")


def test_attraction_key_merges_spelling_variants():
    k = fl_fdacs.attraction_key
    assert k("Harry Potter & the Forbidden Journey") == k("Harry Potter and the Forbidden Journey")
    assert k("Mission: SPACE") == k("Mission Space")
    assert k("Space Mtn.") == k("Space Mountain")


def test_to_records_links_events_to_assets():
    _, entries = parsed()
    assets, events = fl_fdacs.to_records(entries)
    asset_ids = {a["id"] for a in assets}
    assert len(events) == len(entries)
    assert all(ev["asset_id"] in asset_ids for ev in events if ev["asset_id"])
    assert all(ev["kind"] == "incident" for ev in events)


def test_article_before_age_is_stripped_without_eating_ride_names():
    lines = [
        "3rd Quarter 2025 (July - September 2025)",
        "Sea World: 7/14/25 Kraken, a 22-year-old patron, with reported prior medical conditions experienced a medical illness",
        "Disney World: 7/11/26 Humunga Kowabunga, 25 yof, guest injured right leg",
    ]
    _, entries = fl_fdacs.parse_lines(lines)
    assert [e["attraction"] for e in entries] == ["Kraken", "Humunga Kowabunga"]
    assert entries[0]["age"] == 22
