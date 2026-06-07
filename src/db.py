"""SQLite schema and helpers for the iNaturalist pipeline."""

import sqlite3
from contextlib import contextmanager

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS property_obs (
    id            INTEGER PRIMARY KEY,
    uuid          TEXT,
    observed_on   DATE,
    observed_at   TEXT,
    taxon_id      INTEGER,
    taxon_name    TEXT,
    common_name   TEXT,
    iconic_taxon  TEXT,
    rank          TEXT,
    quality_grade TEXT,
    user_login    TEXT,
    user_name     TEXT,
    latitude      REAL,
    longitude     REAL,
    url           TEXT,
    created_at    TEXT,
    photo_url     TEXT,
    photo_attribution TEXT,
    photo_license TEXT
);
CREATE INDEX IF NOT EXISTS idx_property_taxon ON property_obs(taxon_id);
CREATE INDEX IF NOT EXISTS idx_property_observed ON property_obs(observed_on);

CREATE TABLE IF NOT EXISTS county_obs (
    id            INTEGER PRIMARY KEY,
    observed_on   DATE,
    taxon_id      INTEGER,
    taxon_name    TEXT,
    common_name   TEXT,
    iconic_taxon  TEXT,
    quality_grade TEXT,
    user_login    TEXT
);
CREATE INDEX IF NOT EXISTS idx_county_taxon ON county_obs(taxon_id);

CREATE TABLE IF NOT EXISTS species_stats (
    taxon_id           INTEGER PRIMARY KEY,
    taxon_name         TEXT,
    common_name        TEXT,
    county_obs_count   INTEGER,
    state_obs_count    INTEGER,
    county_first_date  DATE,
    state_first_date   DATE,
    property_first_date DATE,
    property_obs_count INTEGER,
    is_county_first    INTEGER,
    state_rarity_rank  INTEGER,
    cached_at          TEXT
);

CREATE TABLE IF NOT EXISTS sync_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source              TEXT,
    synced_at           TEXT,
    last_obs_created_at TEXT,
    observations_added  INTEGER,
    new_species_added   INTEGER
);
"""


@contextmanager
def connect():
    """Yield a connection with row access by column name; commits on exit."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    # WAL lets a reader (e.g. report.py) run alongside a writer (sync.py);
    # busy_timeout makes brief lock contention wait instead of erroring.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Columns added after the first schema shipped; applied to existing DBs.
_MIGRATIONS = {
    "property_obs": ["photo_url TEXT", "photo_attribution TEXT", "photo_license TEXT"],
}


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)
        for table, cols in _MIGRATIONS.items():
            existing = {r["name"] for r in
                        conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for coldef in cols:
                name = coldef.split()[0]
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")


def max_id(conn, table):
    """Highest observation id stored — the cursor for id_above pagination."""
    row = conn.execute(f"SELECT MAX(id) AS m FROM {table}").fetchone()
    return row["m"] or 0


def last_sync(conn, source):
    """Most recent sync_log row for a source, or None."""
    return conn.execute(
        "SELECT * FROM sync_log WHERE source = ? ORDER BY id DESC LIMIT 1",
        (source,),
    ).fetchone()


def record_sync(conn, source, last_obs_created_at, added, new_species):
    conn.execute(
        "INSERT INTO sync_log (source, synced_at, last_obs_created_at, "
        "observations_added, new_species_added) "
        "VALUES (?, datetime('now'), ?, ?, ?)",
        (source, last_obs_created_at, added, new_species),
    )
