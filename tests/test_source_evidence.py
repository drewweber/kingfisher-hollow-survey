import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import analyze


def _inventory():
    property_obs = pd.DataFrame(
        [
            (102, 41, "Luna Moth", "Actias luna", "Insecta", "species", "2026-06-20",
             "2026-06-20T21:00:00", "observer", "https://www.inaturalist.org/observations/102"),
            (101, 41, "Luna Moth", "Actias luna", "Insecta", "species", "2026-06-01",
             "2026-06-01T21:00:00", "observer", "https://www.inaturalist.org/observations/101"),
        ],
        columns=["id", "taxon_id", "common_name", "taxon_name", "iconic_taxon",
                 "rank", "observed_on", "observed_at", "user_login", "url"],
    )
    property_obs["observed_on"] = pd.to_datetime(property_obs["observed_on"])
    property_obs["quality_grade"] = ["research", "needs_id"]
    birds = pd.DataFrame(
        [(1700, "Wood Thrush", "Hylocichla mustelina", "2026-07-14", "S12345"),
         (1701, "Song Sparrow", "Melospiza melodia", None, pd.NA)],
        columns=["taxon_order", "common_name", "taxon_name", "date", "sub_id"],
    )
    birds["date"] = pd.to_datetime(birds["date"])
    return analyze.overview_observations(property_obs, birds)


class SourceHistoryTests(unittest.TestCase):
    def test_life_list_retains_source_evidence_without_inventing_bird_history(self):
        # Group and taxonomy enrichment are unrelated to the source record.
        with patch.object(analyze, "_group_inputs", return_value=(set(), set(), {})), \
                patch.object(analyze, "_join_taxonomy",
                             side_effect=lambda rows: rows.assign(family_name="")):
            life = analyze.life_list(_inventory()).set_index("label")

        self.assertEqual(len(life), 3)
        self.assertTrue(pd.isna(life.loc["Wood Thrush", "last_seen"]))
        self.assertTrue(pd.isna(life.loc["Wood Thrush", "observations"]))
        self.assertTrue(pd.isna(life.loc["Wood Thrush", "observers"]))
        self.assertEqual(life.loc["Wood Thrush", "first_seen"], pd.Timestamp("2026-07-14"))
        self.assertEqual(life.loc["Wood Thrush", "source"], "eBird")
        self.assertEqual(life.loc["Wood Thrush", "source_url"], "https://ebird.org/checklist/S12345")
        self.assertFalse(life.loc["Wood Thrush", "repeat_history_known"])
        self.assertTrue(pd.isna(life.loc["Song Sparrow", "source_url"]))
        self.assertTrue(pd.isna(life.loc["Song Sparrow", "first_seen"]))

        self.assertEqual(life.loc["Luna Moth", "observations"], 2)
        self.assertEqual(life.loc["Luna Moth", "observers"], 1)
        self.assertEqual(life.loc["Luna Moth", "last_seen"], pd.Timestamp("2026-06-20"))
        self.assertEqual(life.loc["Luna Moth", "source"], "iNaturalist")
        self.assertEqual(life.loc["Luna Moth", "source_url"], "https://www.inaturalist.org/observations/101")
        self.assertTrue(life.loc["Luna Moth", "repeat_history_known"])

    def test_inventory_history_retains_dated_bird_evidence(self):
        firsts = analyze.firsts_timeline(_inventory())

        self.assertEqual(firsts["label"].tolist(), ["Luna Moth", "Wood Thrush"])
        self.assertEqual(firsts["cumulative"].tolist(), [1, 2])
        self.assertEqual(firsts["source"].tolist(), ["iNaturalist", "eBird"])
        self.assertEqual(firsts["source_url"].iloc[1], "https://ebird.org/checklist/S12345")
        self.assertEqual(firsts["repeat_history_known"].tolist(), [True, False])

    def test_life_list_rows_do_not_count_as_reporting_or_monthly_detections(self):
        combined = _inventory()

        daily = analyze.obs_per_day(combined).set_index("observed_on")
        self.assertEqual(daily["observations"].sum(), 2)
        self.assertEqual(daily.loc["2026-06-14", "observations"], 0)
        self.assertEqual(daily.index.max(), pd.Timestamp("2026-06-20"))
        self.assertEqual(analyze.phenology(combined).index.tolist(), ["Luna Moth"])

    def test_combined_summary_counts_species_across_sources_and_observations_separately(self):
        summary = analyze.summary(_inventory())

        self.assertEqual(summary["species"], 3)
        self.assertEqual(summary["observations"], 2)
        self.assertEqual(summary["observers"], 1)
        self.assertEqual(summary["research_grade"], 1)
        self.assertEqual(summary["latest_obs"], pd.Timestamp("2026-06-20"))

    def test_reporting_average_uses_calendar_dates_and_starts_at_first_record(self):
        records = pd.DataFrame(
            {"observed_on": pd.to_datetime(["2026-06-01", "2026-06-01", "2026-07-01", None])},
        )

        daily = analyze.obs_per_day(records).set_index("observed_on")

        self.assertEqual(len(daily), 31)
        self.assertEqual(daily.loc["2026-06-01", "rolling_30d"], 2)
        self.assertEqual(daily.loc["2026-06-02", "observations"], 0)
        self.assertEqual(daily.loc["2026-06-02", "rolling_30d"], 1)
        self.assertAlmostEqual(daily.loc["2026-06-30", "rolling_30d"], 2 / 30)
        self.assertAlmostEqual(daily.loc["2026-07-01", "rolling_30d"], 1 / 30)
        self.assertTrue(analyze.obs_per_day(records.iloc[[-1]]).empty)


class PlantGapEvidenceTests(unittest.TestCase):
    def test_candidate_counts_include_taxa_beyond_the_display_limit(self):
        region = pd.DataFrame(
            [
                (1, "Acer saccharum", 110, "Angiosperm", 0, None),
                (2, "Acer platanoides", 100, "Angiosperm", 1, None),
                (3, "Ligustrum vulgare", 99, "Angiosperm", None, "introduced"),
                (4, "Cosmarium moniliforme", 98, "Bryophyte", None, None),
                (5, "Micrasterias americana", 97, "Bryophyte", None, None),
                (6, "Leucobryum glaucum", 90, "Bryophyte", None, None),
                (7, "Betula alleghaniensis", 80, "Angiosperm", None, None),
                (8, "Tsuga canadensis", 70, "Gymnosperm", None, None),
            ],
            columns=["taxon_id", "taxon_name", "region_count", "plant_group",
                     "introduced", "establishment_means"],
        ).assign(common_name=None)
        region["introduced"] = region["introduced"].astype("Int64")
        recorded = pd.DataFrame({"taxon_id": [1, 2]})

        with patch.object(analyze, "_load_table", return_value=region):
            gap = analyze.plant_gap(recorded, n=1)

        self.assertEqual(gap["region_total"], 6)
        self.assertEqual(gap["have"], 1)
        self.assertEqual(gap["missing_count"], 5)
        self.assertEqual(gap["field_missing_count"], 3)
        self.assertEqual(gap["microscopic_missing_count"], 2)
        self.assertEqual(gap["missing"]["taxon_id"].tolist(), [6])
        self.assertEqual(gap["microscopic"]["taxon_id"].tolist(), [4])


class MonthlyMothEvidenceTests(unittest.TestCase):
    def test_monthly_counts_share_session_dates_across_midnight(self):
        records = pd.DataFrame(
            {
                "taxon_id": [1, 2, 3],
                "id": [101, 102, 103],
                "observed_on": pd.to_datetime(["2026-07-31", "2026-08-01", "2026-08-01"]),
                "observed_at": ["2026-07-31T23:30:00-04:00", "2026-08-01T02:00:00-04:00", None],
            },
        )
        moths = pd.DataFrame({"taxon_id": [1, 2, 3]})

        months = analyze.monthly_survey_summary(records, moths)
        july, august = months[6:8]
        counts = ["obs_count", "species_count", "new_species_count", "nights_surveyed"]

        self.assertEqual([july[key] for key in counts], [2, 2, 2, 1])
        self.assertEqual([august[key] for key in counts], [1, 1, 1, 1])
