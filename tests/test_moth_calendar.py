import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import analyze  # noqa: E402
import viz  # noqa: E402


class MothNightlySpeciesTests(unittest.TestCase):
    def setUp(self):
        self.moths = pd.DataFrame({"taxon_id": [1, 2, 3]})

    def test_counts_distinct_species_by_evening_session(self):
        observations = pd.DataFrame(
            [
                {
                    "id": 1,
                    "taxon_id": 1,
                    "observed_on": "2026-06-11",
                    "observed_at": "2026-06-11T22:15:00-04:00",
                },
                {
                    "id": 2,
                    "taxon_id": 1,
                    "observed_on": "2026-06-11",
                    "observed_at": "2026-06-11T23:10:00-04:00",
                },
                {
                    "id": 3,
                    "taxon_id": 2,
                    "observed_on": "2026-06-12",
                    "observed_at": "2026-06-12T05:30:00-04:00",
                },
                {
                    "id": 4,
                    "taxon_id": 3,
                    "observed_on": "2026-06-12",
                    "observed_at": "2026-06-12T21:00:00-04:00",
                },
                {
                    "id": 5,
                    "taxon_id": 3,
                    "observed_on": "2026-06-13",
                    "observed_at": None,
                },
                {
                    "id": 6,
                    "taxon_id": 99,
                    "observed_on": "2026-06-11",
                    "observed_at": "2026-06-11T22:00:00-04:00",
                },
            ]
        )
        observations["observed_on"] = pd.to_datetime(
            observations["observed_on"]
        )

        result = analyze.moth_nightly_species(observations, self.moths)

        self.assertEqual(
            result.to_dict("records"),
            [
                {
                    "night": pd.Timestamp("2026-06-11"),
                    "species_count": 2,
                    "observation_count": 3,
                },
                {
                    "night": pd.Timestamp("2026-06-12"),
                    "species_count": 1,
                    "observation_count": 1,
                },
                {
                    "night": pd.Timestamp("2026-06-13"),
                    "species_count": 1,
                    "observation_count": 1,
                },
            ],
        )

    def test_empty_input_has_stable_columns(self):
        observations = pd.DataFrame(
            columns=["id", "taxon_id", "observed_on", "observed_at"]
        )
        result = analyze.moth_nightly_species(observations, self.moths)

        self.assertTrue(result.empty)
        self.assertEqual(
            list(result.columns),
            ["night", "species_count", "observation_count"],
        )

    def test_calendar_includes_visible_and_nonvisual_values(self):
        nightly = pd.DataFrame(
            [
                {
                    "night": pd.Timestamp("2025-07-03"),
                    "species_count": 12,
                    "observation_count": 18,
                },
                {
                    "night": pd.Timestamp("2026-06-11"),
                    "species_count": 44,
                    "observation_count": 61,
                },
            ]
        )

        html = viz.nightly_species_calendar(nightly)

        self.assertIn("data-plotly-chart", html)
        self.assertIn("Night-by-night data (2 reporting nights)", html)
        self.assertIn("12</td>", html)
        self.assertIn("44</td>", html)
        self.assertIn("Blank dates have no moth report", html)

    def test_calendar_empty_state_explains_next_step(self):
        html = viz.nightly_species_calendar(pd.DataFrame())

        self.assertIn("No nightly moth reports yet", html)
        self.assertIn("Add observations", html)


if __name__ == "__main__":
    unittest.main()
