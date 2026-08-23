import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import analyze  # noqa: E402
import fetch  # noqa: E402


def _regional_frame(rows):
    return pd.DataFrame(
        rows,
        columns=["taxon_id", "taxon_name", "common_name", "region_count"],
    )


class RegionalTargetPolicyTests(unittest.TestCase):
    def test_reptile_policy_filters_exotics_before_totals_and_limit(self):
        reptiles = pd.DataFrame({"taxon_id": [39771]})
        region = _regional_frame([
            (32158, "Python regius", "Ball Python", 300),
            (34675, "Eublepharis macularius", "Common Leopard Gecko", 290),
            (200209, "Correlophus ciliatus", "Crested Giant Gecko", 280),
            (26159, "Alligator mississippiensis", "American Alligator", 270),
            (116461, "Anolis sagrei", "Brown Anole", 260),
            (1544605, "Terrapene triunguis", "Three-toed Box Turtle", 250),
            (39782, "Trachemys scripta", "Pond Slider", 240),
            (39814, "Terrapene carolina", "Common Box Turtle", 230),
            (39858, "Graptemys geographica", "Northern Map Turtle", 220),
            (30746, "Crotalus horridus", "Timber Rattlesnake", 210),
            (39771, "Chrysemys picta", "Painted Turtle", 200),
            (28557, "Storeria occipitomaculata", "Red-bellied Snake", 3),
            (27137, "Coluber constrictor", "North American Racer", 1),
        ])

        with patch.object(analyze, "_load_table", return_value=region):
            gap = analyze.reptile_gap(reptiles, n=2)

        self.assertEqual(3, gap["region_total"])
        self.assertEqual(1, gap["have"])
        self.assertEqual(2, gap["missing_count"])
        self.assertEqual([28557, 27137], gap["missing"]["taxon_id"].tolist())

    def test_amphibian_policy_rejects_pet_and_transported_taxa(self):
        amphibians = pd.DataFrame({"taxon_id": [24268]})
        region = _regional_frame([
            (26777, "Ambystoma mexicanum", "Axolotl", 100),
            (21121, "Dendrobates auratus", "Green-and-black Poison Dart Frog", 90),
            (1668858, "Dryophytes cinereus", "Green Treefrog", 80),
            (24268, "Pseudacris crucifer", "Spring Peeper", 70),
            (66012, "Lithobates sylvaticus", "Wood Frog", 2),
        ])

        with patch.object(analyze, "_load_table", return_value=region):
            gap = analyze.amphibian_gap(amphibians, n=1)

        self.assertEqual(2, gap["region_total"])
        self.assertEqual(1, gap["have"])
        self.assertEqual(1, gap["missing_count"])
        self.assertEqual([66012], gap["missing"]["taxon_id"].tolist())

    def test_mammal_policy_rejects_domestic_zoo_and_fossil_taxa(self):
        mammals = pd.DataFrame({"taxon_id": [42051]})
        region = _regional_frame([
            (118552, "Felis catus", "Domestic Cat", 500),
            (47144, "Canis familiaris", "Domestic Dog", 490),
            (74113, "Bos taurus", "Domestic Cattle", 480),
            (74831, "Panthera uncia", "Snow Leopard", 470),
            (194816, "Mammut americanum", "American Mastodon", 460),
            (42051, "Canis latrans", "Coyote", 300),
            (41880, "Mephitis mephitis", "Striped Skunk", 4),
        ])

        with patch.object(analyze, "_load_table", return_value=region):
            gap = analyze.mammal_gap(mammals, n=1)

        self.assertEqual(2, gap["region_total"])
        self.assertEqual(1, gap["have"])
        self.assertEqual(1, gap["missing_count"])
        self.assertEqual([41880], gap["missing"]["taxon_id"].tolist())


class WildRosterSyncTests(unittest.TestCase):
    def test_property_rosters_request_non_captive_observations(self):
        with patch.object(fetch, "_sync_roster", return_value=1) as sync:
            fetch.sync_mammals()
            fetch.sync_amphibians()
            fetch.sync_reptiles()

        self.assertEqual(3, sync.call_count)
        for call in sync.call_args_list:
            self.assertEqual("false", call.kwargs["captive"])
            self.assertNotIn("introduced", call.kwargs)

    def test_regional_rosters_request_wild_non_introduced_observations(self):
        with patch.object(fetch, "_property_center", return_value=(42.27, -76.49)), \
                patch.object(fetch, "_sync_roster", return_value=1) as sync:
            fetch.sync_region_mammals()
            fetch.sync_region_amphibians()
            fetch.sync_region_reptiles()

        self.assertEqual(3, sync.call_count)
        for call in sync.call_args_list:
            self.assertEqual("false", call.kwargs["captive"])
            self.assertEqual("false", call.kwargs["introduced"])


if __name__ == "__main__":
    unittest.main()
