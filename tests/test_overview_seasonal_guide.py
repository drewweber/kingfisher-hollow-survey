import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import analyze
import viz


class SeasonalGuideTests(unittest.TestCase):
    def guide(self, rows):
        with patch.object(analyze, "add_group_column", side_effect=lambda df: df):
            return analyze.seasonal_guide(pd.DataFrame(rows))

    def records(self, taxon_id, group, dates, iconic="Insecta", **extra):
        return [dict(id=taxon_id * 100 + i, taxon_id=taxon_id, group=group,
                     common_name=f"Example {taxon_id}", taxon_name=f"Species {taxon_id}",
                     observed_on=date, iconic_taxon=iconic, rank="species", **extra)
                for i, date in enumerate(dates)]

    def test_cross_group_quota_resists_moth_volume(self):
        rows = []
        groups = [("Plants", "Plantae"), ("Fungi", "Fungi"),
                  ("Amphibians", "Amphibia"), ("Butterflies", "Insecta"),
                  ("Dragonflies and Damselflies", "Insecta"), ("Beetles", "Insecta"),
                  ("Mammals", "Mammalia"), ("Moths", "Insecta")]
        for tid, (group, iconic) in enumerate(groups, 1):
            rows.extend(self.records(tid, group, ["2025-07-01", "2026-07-02"], iconic))
        rows.extend(self.records(99, "Moths", pd.date_range("2026-07-01", periods=30)))
        examples = self.guide(rows)["seasons"][1]["examples"]
        self.assertEqual([e["group"] for e in examples], list(analyze.GUIDE_GROUPS[:6]))
        self.assertTrue(all(e["recording_days"] == 2 for e in examples))

    def test_selection_uses_distinct_days_and_is_deterministic(self):
        rows = self.records(1, "Plants", ["2026-03-01"] * 20, "Plantae")
        rows += self.records(2, "Plants", ["2026-03-01", "2026-05-01"], "Plantae")
        rows += self.records(3, "Plants", ["2026-03-01", "2026-04-01", "2026-06-01"], "Plantae")
        guide = self.guide(rows)
        self.assertEqual(guide, self.guide(list(reversed(rows))))
        chosen = guide["seasons"][0]["examples"][0]
        self.assertEqual(chosen["taxon_id"], 2)
        self.assertEqual(chosen["recorded_months"], [3, 5])  # April is not invented.
        self.assertEqual(chosen["recording_days"], 2)
        self.assertEqual(chosen["years"], [2026])
        self.assertEqual(chosen["sample_id"], 201)
        self.assertEqual(chosen["sample_date"], pd.Timestamp("2026-05-01"))

    def test_seasons_are_independent_and_winter_wrap_follows_calendar_order(self):
        rows = self.records(1, "Moths", ["2026-03-01", "2026-03-02", "2026-07-01",
                                            "2026-07-02", "2026-10-01", "2026-10-02",
                                            "2025-12-01", "2026-01-01"])
        rows += self.records(2, "Mammals", ["2025-12-01", "2026-01-01"], "Mammalia")
        guide = self.guide(rows)
        self.assertEqual([s["name"] for s in guide["seasons"]], ["Spring", "Summer", "Autumn", "Winter"])
        self.assertEqual(sum(e["group"] == "Moths" for s in guide["seasons"] for e in s["examples"]), 4)
        self.assertEqual(len(guide["seasons"][3]["examples"]), 2)
        self.assertEqual(guide["seasons"][3]["examples"][0]["recorded_months"], [12, 1])

    def test_sparse_missing_dates_and_bird_life_lists_never_fill_gaps(self):
        rows = self.records(1, "Plants", ["2026-04-01", None], "Plantae", repeat_history_known=True)
        rows += self.records(2, "Birds", ["2026-04-01", "2026-04-02"], "Aves", repeat_history_known=False)
        rows += self.records(3, "Moths", ["2026-04-01", "2026-04-02"], repeat_history_known=False)
        guide = self.guide(rows)
        self.assertTrue(all(not s["examples"] for s in guide["seasons"]))
        html = viz.seasonal_guide(guide)
        self.assertEqual(html.count("No examples selected under this guide’s criteria"), 4)
        self.assertNotIn("nan", html)
        self.assertIn("not evidence that other wildlife is absent", html)
        self.assertEqual(len(self.guide([])["seasons"]), 4)

    def test_html_preserves_evidence_and_needs_no_chart_runtime(self):
        rows = self.records(1, "Fungi", ["2025-08-01", "2026-08-02"], "Fungi")
        for row in rows:
            row["common_name"] = "A <fungus> & allies"
        html = viz.seasonal_guide(self.guide(rows))
        self.assertIn("A &lt;fungus&gt; &amp; allies", html)
        self.assertIn("https://www.inaturalist.org/observations/101", html)
        self.assertIn("2 distinct days · 2025, 2026", html)
        self.assertIn("Linked record: 2026-08-02", html)
        self.assertIn("Recorded in Aug", html)
        self.assertIn("all recorded life stages", html)
        self.assertIn("<summary", html)
        self.assertIn('<ul role="list"', html)
        self.assertNotIn("<script", html)
        self.assertNotIn("data-plotly-chart", html)


if __name__ == "__main__":
    unittest.main()
