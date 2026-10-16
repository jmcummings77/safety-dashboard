-- Normalized store shared by every source adapter.
-- An "asset" is any piece of public safety-critical equipment (ride, bridge, elevator, dam...).
-- An "event" is anything filed about an asset: an incident report, an inspection, a condition rating.

CREATE TABLE IF NOT EXISTS sources (
    id           TEXT PRIMARY KEY,          -- e.g. 'fl_fdacs_exempt'
    name         TEXT NOT NULL,
    agency       TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,             -- 'US-FL', 'US', ...
    domain       TEXT NOT NULL,             -- 'amusement_ride' | 'bridge' | ...
    url          TEXT NOT NULL,
    fetched_at   TEXT NOT NULL,             -- ISO timestamp of last pull
    as_of        TEXT,                      -- date the publisher says the data is current to
    notes        TEXT
);

CREATE TABLE IF NOT EXISTS assets (
    id           TEXT PRIMARY KEY,          -- '<source>:<natural key>'
    source_id    TEXT NOT NULL REFERENCES sources(id),
    domain       TEXT NOT NULL,
    name         TEXT NOT NULL,
    operator     TEXT,                      -- park / bridge owner
    region       TEXT,                      -- state or similar
    lat          REAL,
    lon          REAL,
    attrs        TEXT                       -- JSON blob of domain-specific fields
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id    TEXT NOT NULL REFERENCES sources(id),
    asset_id     TEXT REFERENCES assets(id),
    kind         TEXT NOT NULL,             -- 'incident' | 'inspection'
    date         TEXT,                      -- ISO date
    severity     TEXT,                      -- normalized: 'fatal','serious','moderate','minor' / 'good','fair','poor'
    summary      TEXT,
    attrs        TEXT                       -- JSON blob of domain-specific fields
);

CREATE INDEX IF NOT EXISTS events_asset ON events(asset_id);
CREATE INDEX IF NOT EXISTS events_date ON events(date);
