# Safety Filings Tracker

[![CI](https://github.com/jmcummings77/safety-dashboard/actions/workflows/ci.yml/badge.svg)](https://github.com/jmcummings77/safety-dashboard/actions/workflows/ci.yml)
[![Deploy site](https://github.com/jmcummings77/safety-dashboard/actions/workflows/pages.yml/badge.svg)](https://github.com/jmcummings77/safety-dashboard/actions/workflows/pages.yml)
[![Refresh data](https://github.com/jmcummings77/safety-dashboard/actions/workflows/refresh-data.yml/badge.svg)](https://github.com/jmcummings77/safety-dashboard/actions/workflows/refresh-data.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Live dashboard: https://jmcummings77.github.io/safety-dashboard/**

A dashboard of publicly filed safety records for public equipment. It starts with theme park rides and highway bridges, and is built to take on any other equipment with usable public data (dams, elevators, ski lifts...).

| Domain | Source | What it contains |
|---|---|---|
| Theme park rides | Florida Dept. of Agriculture & Consumer Services, *MOU Exempt Facilities Report* | ~900 injury and illness reports from Florida's largest parks, 2001 to present, updated quarterly |
| Bridges | Federal Highway Administration, *National Bridge Inventory* | Inspection dates, inspection intervals and condition ratings for all 624k US highway bridges, updated annually |

## What the data can and can't say

- **Ride records are incident reports, not maintenance logs.** Few states publish ride maintenance or inspection records. Florida's reports are filed by the parks themselves, cover only incidents with a hospital stay of 24 hours or more, and do not establish cause. Many are medical episodes in guests with pre-existing conditions.
- **Bridge records are real inspection data.** "Poor" means the lowest of the deck, superstructure, substructure or culvert ratings is 4 or below on FHWA's 0–9 scale. It does not mean a bridge is unsafe; unsafe bridges are closed or load-posted. "Overdue" is computed here: more than 3 months past the required interval as of the state's submission (`OVERDUE_GRACE_MONTHS` in `pipeline/build.py`).
- The Florida PDF is free text, so age, sex, attraction and severity are extracted heuristically. Check the original filing before citing a record.

The **Data sources** tab on the dashboard lists candidate sources for other states and equipment types.

## How it works

```
pipeline/
  schema.sql          shared SQLite schema: sources → assets → events
  build.py            fetch every source, load data/safety.db, export site/data.js
  sources/
    fl_fdacs.py       Florida ride incident reports (PDF → records)
    fhwa_nbi.py       National Bridge Inventory (CSV → records)
site/
  index.html          static dashboard, no build step
  data.js             exported data (committed so the site deploys without running the pipeline)
  us-states.js        state outlines for the bridge map (us-atlas)
tests/                pytest suite with small fixtures cut from the real source files
```

Every source adapter maps its records onto the same three tables: **sources** (who published it), **assets** (the ride or bridge) and **events** (an incident or an inspection, with a normalized severity). The dashboard reads a compact JSON export rather than the database.

GitHub Actions:

- **CI** runs ruff (lint and format) and pytest on Python 3.9 and 3.12 for every push and pull request.
- **Deploy site** publishes `site/` to GitHub Pages when it changes on `main`.
- **Refresh data** re-downloads every source each Monday, commits `site/data.js` only if the data changed, and redeploys.

## Development

```bash
make install   # create .venv, install dev dependencies, install pre-commit hooks
make test      # pytest with coverage
make lint      # ruff check + format check
make build     # run the pipeline using cached downloads in raw/
make refresh   # re-download every source, then build
make serve     # http://localhost:8765
```

The first `make build` downloads about 55 MB and writes a ~500 MB SQLite database to `data/`. Both `raw/` and `data/` are git-ignored.

FHWA publishes a new NBI release each year. To move to it, bump `YEAR` in `pipeline/sources/fhwa_nbi.py`.

### Adding a source

1. Add `pipeline/sources/<id>.py` with a `SOURCE` dict (id, name, agency, jurisdiction, domain, url, notes) and a `parse()` function.
2. Map its records onto assets and events (`incident` or `inspection`, with a normalized `severity`).
3. Add a test with a small fixture cut from the real file.
4. Call it from `build.py` and add the summary the dashboard needs to the export.

## License

Code is MIT licensed; see [LICENSE](LICENSE). The data is public record, published by the Florida Department of Agriculture and Consumer Services and the US Federal Highway Administration. Map outlines are from [us-atlas](https://github.com/topojson/us-atlas) (ISC).
