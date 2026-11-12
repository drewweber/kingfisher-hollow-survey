import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import analyze
from moth_story import build_story


class MothStoryTests(unittest.TestCase):
    def test_empty_story_covers_every_month(self):
        story = build_story(pd.DataFrame(), pd.DataFrame())

        self.assertEqual([row["month"] for row in story["monthly"]], list(range(1, 13)))
        self.assertTrue(all(row["taxa"] == row["records"] == row["reporting_dates"] == 0
                            and row["years"] == [] for row in story["monthly"]))
        self.assertEqual(len(story["comparisons"]), 11)
        self.assertEqual(story["discovery"], [])
        self.assertEqual(story["timing"], [])
        self.assertEqual(story["frequency"], {"once": 0, "twice": 0, "three_plus": 0})
        self.assertEqual(story["years"], [])
        self.assertIsNone(story["first_date"])
        self.assertIsNone(story["last_date"])

    def test_pooled_months_and_history_share_eligible_local_records(self):
        moths = pd.DataFrame({
            "taxon_id": [1, 2, 3, 4, 5],
            "taxon_name": ["Taxon a", "Taxon b", "Taxon c", "Taxon d", "Taxon e"],
            "common_name": ["A", "B", None, "D", "E"],
        })
        observations = pd.DataFrame([
            (1, "2025-07-01", "2025-07-01T01:15:00-04:00", "adult", True),
            (1, "2025-07-01", None, "larva", True),
            (2, "2025-07-01", None, None, True),
            (1, "2026-07-01", None, "adult", True),
            (1, "2026-08-01", None, None, True),
            (3, "2026-08-01", None, None, True),
            (3, "2026-08-02", None, None, True),
            (4, "2026-08-03", None, None, False),
            (5, None, None, None, True),
            (99, "2024-06-01", None, None, True),
        ], columns=["taxon_id", "observed_on", "observed_at", "life_stage", "repeat_history_known"])

        story = build_story(observations, moths)
        json.dumps(story, allow_nan=False)
        self.assertEqual(story["years"], [2025, 2026])
        self.assertEqual((story["first_date"], story["last_date"]), ("2025-07-01", "2026-08-02"))
        self.assertEqual(story["monthly"][5]["records"], 0)
        self.assertEqual(story["monthly"][6], {
            "month": 7, "name": "July", "taxa": 2, "records": 4,
            "reporting_dates": 2, "years": [2025, 2026],
        })
        self.assertEqual(story["comparisons"][6], {
            "first_month": 7, "second_month": 8, "shared": 1,
            "first_only": 1, "second_only": 1,
        })
        self.assertEqual(story["discovery"], [
            {"date": "2025-07-01", "cumulative_taxa": 2},
            {"date": "2026-07-01", "cumulative_taxa": 2},
            {"date": "2026-08-01", "cumulative_taxa": 3},
            {"date": "2026-08-02", "cumulative_taxa": 3},
        ])
        self.assertEqual(story["frequency"], {"once": 1, "twice": 1, "three_plus": 1})
        timing = {row["id"]: row for row in story["timing"]}
        self.assertEqual(set(timing), {1, 2, 3, 4, 5})
        self.assertEqual(timing[1]["monthly_records"], [0, 0, 0, 0, 0, 0, 3, 1, 0, 0, 0, 0])
        self.assertEqual(timing[1]["stages"], ["adult", "larva"])
        self.assertIsNone(timing[3]["common_name"])
        self.assertEqual(timing[5]["monthly_records"], [0] * 12)


class MothFamilyTests(unittest.TestCase):
    def setUp(self):
        self.moths = pd.DataFrame({"taxon_id": [1, 2, 3, 4]})
        self.meta = pd.DataFrame({
            "taxon_id": [1, 2, 3, 4, 5, 6, 7],
            "family_name": ["A", "A", "A", "B", "B", "C", "C"],
            "family_common": [None, "Family A", None, None, None, None, None],
        })
        self.region = pd.DataFrame({"taxon_id": [1, 5, 6, 7, 7]})
        self.county = pd.DataFrame({"taxon_id": [1, 2, 5]})

    def breakdown(self, region, county, n=None):
        tables = {"taxon_meta": self.meta, "region_moth_taxa": region, "county_moth_taxa": county}
        with patch.object(analyze, "_load_table", side_effect=tables.__getitem__):
            return analyze.moth_family_breakdown(self.moths, n=n)

    def test_regional_denominator_and_gap_use_actual_membership(self):
        rows = self.breakdown(self.region, self.county)
        self.assertEqual(rows["family_name"].tolist(), ["A", "B", "C"])
        self.assertEqual(rows.iloc[0].to_dict(), {
            "family_name": "A", "recorded": 3, "region_total": 1, "overlap": 1,
            "gap": 0, "label": "Family A", "reference_scope": "region",
        })
        self.assertEqual(rows["gap"].tolist(), [0, 1, 2])
        self.assertEqual(self.breakdown(self.region, self.county, n=1)["family_name"].tolist(), ["A"])

    def test_county_fallback_and_local_only_family_breadth(self):
        county = self.breakdown(pd.DataFrame(), self.county)
        self.assertEqual(county["reference_scope"].tolist(), ["county", "county"])
        self.assertEqual(county["overlap"].tolist(), [2, 0])
        local = self.breakdown(pd.DataFrame(), pd.DataFrame())
        self.assertEqual(local["recorded"].tolist(), [3, 1])
        self.assertEqual(local["region_total"].tolist(), [0, 0])
        self.assertTrue(local["reference_scope"].isna().all())


class MothHighlightTests(unittest.TestCase):
    def test_selects_supported_find_and_keeps_the_local_photo_provenance(self):
        moths = pd.DataFrame({
            "taxon_id": [1, 2, 3], "taxon_name": ["A", "B", "C"],
            "common_name": [None, "Bee", None], "obs_count": [2, 700, 1],
            "photo_url": ["representative A", "representative B", "representative C"],
        })
        stats = pd.DataFrame({
            "taxon_id": [1, 3], "state_obs_count": [12, 20], "county_obs_count": [2, 3],
            "is_county_first": [0, 0],
        })
        observations = pd.DataFrame([
            (1, 10, "2026-06-01", None, None, None),
            (1, 11, "2026-06-02", "local A", "local credit", "cc-by"),
            (3, 12, "2026-06-04", None, None, None),
        ], columns=["taxon_id", "id", "observed_on", "photo_url", "photo_attribution", "photo_license"])

        highlights = analyze.moth_highlights(moths, stats, observations).set_index("taxon_id")
        self.assertEqual(highlights.index.tolist(), [1, 3])
        self.assertEqual(highlights.loc[1, [
            "label", "photo_url", "photo_attribution", "photo_license",
            "first_obs_id", "photo_observation_id", "photo_source",
        ]].tolist(), ["A", "local A", "local credit", "cc-by", 10, 11, "local_observation"])
        self.assertEqual(highlights.loc[3, "photo_source"], "representative")
        self.assertTrue(pd.isna(highlights.loc[3, "photo_observation_id"]))
        self.assertTrue(analyze.moth_highlights(moths, pd.DataFrame()).empty)
