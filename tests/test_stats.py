import sqlite3
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import stats  # noqa: E402


class StatsSelectionTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE property_obs (
                taxon_id INTEGER,
                taxon_name TEXT,
                common_name TEXT,
                observed_on TEXT,
                rank TEXT
            );
            CREATE TABLE species_stats (
                taxon_id INTEGER PRIMARY KEY,
                cached_at TEXT
            );
            """
        )
        self.conn.executemany(
            "INSERT INTO property_obs VALUES (?, ?, ?, ?, 'species')",
            [
                (1, "Missing species", "Missing", "2026-01-01"),
                (2, "Oldest species", "Oldest", "2026-01-02"),
                (3, "Newer stale species", "Newer", "2026-01-03"),
                (4, "Fresh species", "Fresh", "2026-01-04"),
            ],
        )
        self.conn.executemany(
            "INSERT INTO species_stats VALUES (?, datetime('now', ?))",
            [(2, "-90 days"), (3, "-60 days"), (4, "-1 day")],
        )

    def tearDown(self):
        self.conn.close()

    def test_limit_prioritizes_missing_then_oldest_stale(self):
        rows = stats._stale_or_missing(self.conn, include_stale=True, limit=2)
        self.assertEqual([row["taxon_id"] for row in rows], [1, 2])

    def test_daily_selection_ignores_stale_cached_rows(self):
        rows = stats._stale_or_missing(self.conn, include_stale=False)
        self.assertEqual([row["taxon_id"] for row in rows], [1])


if __name__ == "__main__":
    unittest.main()
