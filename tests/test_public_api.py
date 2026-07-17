import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import public_api  # noqa: E402


class PublicApiSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE property_obs (
                id INTEGER,
                taxon_id INTEGER,
                taxon_name TEXT,
                common_name TEXT,
                rank TEXT,
                observed_on TEXT,
                observed_at TEXT,
                url TEXT,
                user_login TEXT,
                latitude REAL,
                longitude REAL
            );
            CREATE TABLE moth_taxa (taxon_id INTEGER);
            CREATE TABLE taxon_meta (
                taxon_id INTEGER,
                order_name TEXT,
                family_name TEXT
            );
            """
        )
        self.conn.executemany(
            "INSERT INTO property_obs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    101, 1, "Actias luna", "Luna Moth", "species", "2026-06-11",
                    "2026-06-11T22:14:00-04:00",
                    "https://www.inaturalist.org/observations/101", "private-user",
                    42.2, -76.4,
                ),
                (
                    102, 2, "Examplea micro", None, "species", "2026-06-11",
                    "2026-06-11T23:00:00-04:00", None, "private-user", 42.2, -76.4,
                ),
                (
                    103, 3, "Danaus plexippus", "Monarch", "species", "2026-06-12",
                    "2026-06-12T12:00:00-04:00", None, "private-user", 42.2, -76.4,
                ),
            ],
        )
        # The duplicate join row verifies that observation IDs remain unique.
        self.conn.executemany("INSERT INTO moth_taxa VALUES (?)", [(1,), (1,), (2,)])
        self.conn.executemany(
            "INSERT INTO taxon_meta VALUES (?, ?, ?)",
            [(1, "Lepidoptera", "Saturniidae"), (2, "Lepidoptera", "Tortricidae")],
        )

    def tearDown(self):
        self.conn.close()

    def test_snapshot_is_deduplicated_and_privacy_safe(self):
        snapshot = public_api.snapshot_from_connection(
            self.conn, generated_at="2026-07-17T12:00:00Z"
        )
        self.assertEqual(snapshot["observation_count"], 2)
        self.assertEqual(snapshot["species_count"], 2)
        self.assertEqual(snapshot["night_count"], 1)
        self.assertEqual(snapshot["timezone"], "America/New_York")
        self.assertEqual(snapshot["observations"][0]["observation_id"], 102)
        self.assertIsNone(snapshot["observations"][0]["common_name"])
        for observation in snapshot["observations"]:
            self.assertNotIn("user_login", observation)
            self.assertNotIn("latitude", observation)
            self.assertNotIn("longitude", observation)

    def test_data_version_does_not_change_with_build_time(self):
        first = public_api.snapshot_from_connection(
            self.conn, generated_at="2026-07-17T12:00:00Z"
        )
        second = public_api.snapshot_from_connection(
            self.conn, generated_at="2026-07-18T12:00:00Z"
        )
        self.assertEqual(first["data_version"], second["data_version"])
        self.assertNotEqual(first["generated_at"], second["generated_at"])

    def test_writer_creates_a_valid_compact_json_asset(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "_api-data" / "moths.json"
            payload = public_api.write_snapshot(
                self.conn,
                output_path=output,
                generated_at="2026-07-17T12:00:00Z",
            )
            text = output.read_text(encoding="utf-8")
            self.assertTrue(text.endswith("\n"))
            self.assertIn('"dataset":"kingfisher-hollow-moths"', text)
            self.assertEqual(payload["observation_count"], 2)


if __name__ == "__main__":
    unittest.main()
