import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


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
                    "https://example.com/not-the-source-record", "private-user",
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
            self.assertEqual(
                observation["inat_url"],
                "https://www.inaturalist.org/observations/"
                f"{observation['observation_id']}",
            )

    def test_local_date_is_derived_from_the_timestamp_in_survey_timezone(self):
        self.conn.execute(
            "INSERT INTO property_obs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                104, 4, "Examplea midnight", "Midnight Moth", "species",
                "2026-06-12", "2026-06-12T01:30:00Z", None, "private-user",
                42.2, -76.4,
            ),
        )
        self.conn.execute("INSERT INTO moth_taxa VALUES (?)", (4,))
        self.conn.execute(
            "INSERT INTO taxon_meta VALUES (?, ?, ?)",
            (4, "Lepidoptera", "Noctuidae"),
        )
        snapshot = public_api.snapshot_from_connection(
            self.conn, generated_at="2026-07-17T12:00:00Z"
        )
        observation = next(
            item for item in snapshot["observations"] if item["observation_id"] == 104
        )
        self.assertEqual(observation["observed_on"], "2026-06-11")
        self.assertEqual(snapshot["night_count"], 1)

    def test_timezone_free_timestamp_is_rejected(self):
        self.conn.execute(
            "INSERT INTO property_obs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                105, 5, "Examplea naive", "Naive Moth", "species", "2026-06-12",
                "2026-06-12T01:30:00", None, "private-user", 42.2, -76.4,
            ),
        )
        self.conn.execute("INSERT INTO moth_taxa VALUES (?)", (5,))
        self.conn.execute(
            "INSERT INTO taxon_meta VALUES (?, ?, ?)",
            (5, "Lepidoptera", "Noctuidae"),
        )
        with self.assertRaisesRegex(ValueError, "has no observed_at timezone"):
            public_api.snapshot_from_connection(
                self.conn, generated_at="2026-07-17T12:00:00Z"
            )

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


class PublicApiSummaryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE property_obs (
                taxon_id INTEGER,
                iconic_taxon TEXT,
                rank TEXT
            );
            CREATE TABLE moth_taxa (taxon_id INTEGER);
            CREATE TABLE mammal_taxa (taxon_id INTEGER);
            CREATE TABLE amphibian_taxa (taxon_id INTEGER);
            CREATE TABLE odonate_taxa (taxon_id INTEGER);
            CREATE TABLE butterfly_taxa (taxon_id INTEGER);
            CREATE TABLE sync_log (synced_at TEXT);
            """
        )
        self.conn.executemany(
            "INSERT INTO property_obs VALUES (?, ?, ?)",
            [
                (1, "Plantae", "species"),
                (1, "Plantae", "species"),
                (2, "Insecta", "species"),
                (3, "Aves", "species"),
                (4, "Fungi", "genus"),
                (5, "Mammalia", "subspecies"),
            ],
        )
        self.conn.executemany(
            "INSERT INTO moth_taxa VALUES (?)",
            [(2,), (2,), (7,)],
        )
        self.conn.executemany("INSERT INTO mammal_taxa VALUES (?)", [(5,), (5,)])
        self.conn.execute("INSERT INTO amphibian_taxa VALUES (?)", (6,))
        self.conn.execute("INSERT INTO odonate_taxa VALUES (?)", (8,))
        self.conn.execute("INSERT INTO butterfly_taxa VALUES (?)", (3,))
        self.conn.executemany(
            "INSERT INTO sync_log VALUES (?)",
            [("2026-07-23 22:00:00",), ("2026-07-24 03:00:00",)],
        )
        self.birds = pd.DataFrame(
            [
                {"taxon_name": "Setophaga ruticilla", "common_name": "American Redstart"},
                {"taxon_name": "Catharus fuscescens", "common_name": "Veery"},
                {"taxon_name": "Setophaga ruticilla", "common_name": "American Redstart"},
            ]
        )

    def tearDown(self):
        self.conn.close()

    def test_summary_uses_current_lists_and_deduplicates_the_all_taxa_total(self):
        summary = public_api.summary_from_connection(self.conn, birds=self.birds)
        self.assertEqual(
            summary,
            {
                "birds": 2,
                "moths": 2,
                "mammals": 1,
                "amphibians": 1,
                "odonates": 1,
                "butterflies": 1,
                "totalSpecies": 5,
                "updatedAt": "2026-07-24T03:00:00Z",
            },
        )

    def test_summary_supports_zero_and_empty_datasets(self):
        self.conn.execute("DELETE FROM property_obs")
        self.conn.execute("DELETE FROM moth_taxa")
        self.conn.execute("DELETE FROM mammal_taxa")
        self.conn.execute("DELETE FROM amphibian_taxa")
        self.conn.execute("DELETE FROM odonate_taxa")
        self.conn.execute("DELETE FROM butterfly_taxa")
        empty_birds = pd.DataFrame(columns=["taxon_name", "common_name"])
        summary = public_api.summary_from_connection(
            self.conn,
            birds=empty_birds,
            updated_at="2026-07-24T03:00:00Z",
        )
        self.assertEqual(summary["birds"], 0)
        self.assertEqual(summary["moths"], 0)
        self.assertEqual(summary["mammals"], 0)
        self.assertEqual(summary["amphibians"], 0)
        self.assertEqual(summary["odonates"], 0)
        self.assertEqual(summary["butterflies"], 0)
        self.assertEqual(summary["totalSpecies"], 0)
        self.assertIsInstance(summary["birds"], int)
        self.assertIsInstance(summary["moths"], int)
        self.assertIsInstance(summary["mammals"], int)
        self.assertIsInstance(summary["amphibians"], int)
        self.assertIsInstance(summary["odonates"], int)
        self.assertIsInstance(summary["butterflies"], int)
        self.assertIsInstance(summary["totalSpecies"], int)

    def test_summary_writer_creates_the_generated_api_asset(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "_api-data" / "summary.json"
            payload = public_api.write_summary(
                self.conn,
                output_path=output,
                birds=self.birds,
            )
            self.assertEqual(payload["totalSpecies"], 5)
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                '{"birds":2,"moths":2,"mammals":1,"amphibians":1,'
                '"odonates":1,"butterflies":1,"totalSpecies":5,'
                '"updatedAt":"2026-07-24T03:00:00Z"}\n',
            )


if __name__ == "__main__":
    unittest.main()
