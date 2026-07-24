import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from moth_guilds import (  # noqa: E402
    HOST_INDEX_PATH,
    LOOKBACK_DAYS,
    load_host_index,
    local_flight_signal,
)


class MothGuildSignalTests(unittest.TestCase):
    def setUp(self):
        self.index = {
            "source": {
                "title": "HOSTS",
                "url": "https://data.nhm.ac.uk/dataset/hosts",
            },
            "associations": {
                "Targeta expected": {"host_genera": ["Oenothera"]},
                "Indicata recent": {"host_genera": ["Oenothera"]},
                "Broadia generalist": {
                    "host_genera": [f"Host{index}" for index in range(13)]
                },
            },
        }
        self.today = date(2026, 7, 23)

    def test_recent_exact_host_guild_creates_strong_signal(self):
        signal = local_flight_signal(
            "Targeta expected",
            [{
                "scientific_name": "Indicata recent",
                "common_name": "Recent Indicator",
                "last_seen": "2026-07-23",
                "observation_count": 2,
            }],
            self.index,
            self.today,
        )
        self.assertIsNotNone(signal)
        self.assertEqual("strong", signal["strength"])
        self.assertEqual("Oenothera", signal["guilds"][0]["host_genus"])
        self.assertEqual("Recent Indicator", signal["guilds"][0]["indicators"][0]["common_name"])
        self.assertIn("not proof", signal["caution"])

    def test_signal_expires_after_lookback_window(self):
        signal = local_flight_signal(
            "Targeta expected",
            [{
                "scientific_name": "Indicata recent",
                "common_name": "Old Indicator",
                "last_seen": date(2026, 7, 23).replace(day=23 - LOOKBACK_DAYS),
                "observation_count": 1,
            }],
            self.index,
            self.today,
        )
        self.assertIsNone(signal)

    def test_very_broad_feeder_does_not_change_ranking(self):
        signal = local_flight_signal(
            "Targeta expected",
            [{
                "scientific_name": "Broadia generalist",
                "common_name": "Broad Feeder",
                "last_seen": "2026-07-23",
                "observation_count": 1,
            }],
            self.index,
            self.today,
        )
        self.assertIsNone(signal)

    def test_checked_in_host_index_retains_provenance(self):
        self.assertTrue(HOST_INDEX_PATH.is_file())
        index = load_host_index()
        self.assertTrue(index["source"]["url"].startswith("https://"))
        self.assertIn("Schinia florida", index["associations"])
        self.assertEqual(
            ["Oenothera"],
            index["associations"]["Schinia florida"]["host_genera"],
        )


if __name__ == "__main__":
    unittest.main()
