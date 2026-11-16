"""Calendar overlays preserve real dates, record boundaries, and rolling means."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import analyze
from src import viz


class AnnualActivityTests(unittest.TestCase):
    def chart(self, daily):
        with patch.object(viz, "_html", return_value="<plot>") as render:
            html = viz.per_day(daily)
        return render.call_args.args[0], html

    def test_fixed_calendar_and_partial_years_preserve_record_boundaries(self):
        daily = analyze.obs_per_day(pd.DataFrame({
            "observed_on": pd.to_datetime(["2025-06-15", "2026-11-03"]),
        }))
        fig, html = self.chart(daily)
        self.assertEqual(list(fig.layout.xaxis.range), [1, 366])
        self.assertTrue(fig.layout.xaxis.fixedrange)
        self.assertEqual(list(fig.layout.xaxis.ticktext), viz.MONTHS)
        self.assertEqual([trace.name for trace in fig.data], ["2025 (partial)", "2026 (partial)"])
        self.assertEqual(fig.data[0].customdata[0][0], "2025-06-15")
        self.assertEqual(fig.data[0].customdata[-1][0], "2025-12-31")
        self.assertEqual(fig.data[1].customdata[0][0], "2026-01-01")
        self.assertEqual(fig.data[1].customdata[-1][0], "2026-11-03")
        self.assertIn("Dates outside the available record span are left blank", html)
        self.assertIn("2025 (partial): Jun 15–Dec 31", html)
        self.assertIn("2026 (partial): Jan 01–Nov 03", html)
        self.assertNotEqual(fig.data[0].line.dash, fig.data[1].line.dash)
        self.assertNotEqual(fig.data[0].line.color, fig.data[1].line.color)

    def test_leap_day_is_preserved_without_shifting_later_calendar_dates(self):
        daily = analyze.obs_per_day(pd.DataFrame({
            "observed_on": pd.to_datetime(["2023-02-28", "2024-03-01"]),
        }))
        fig, _ = self.chart(daily)
        positions = {date: x for trace in fig.data
                     for x, (date, _) in zip(trace.x, trace.customdata)}
        self.assertEqual(positions["2023-02-28"], positions["2024-02-28"])
        self.assertEqual(positions["2023-03-01"], positions["2024-03-01"])
        self.assertEqual(positions["2024-02-29"], 60)
        self.assertNotIn(60, fig.data[0].x)
        self.assertEqual(positions["2023-12-31"], 366)

    def test_rolling_mean_crosses_year_boundary_and_uses_calendar_zeroes(self):
        daily = analyze.obs_per_day(pd.DataFrame({
            "observed_on": pd.to_datetime(["2025-12-03", "2025-12-03", "2026-01-01"]),
        }))
        fig, html = self.chart(daily)
        self.assertEqual(fig.data[0].customdata[1], ["2025-12-04", 0])
        self.assertEqual(fig.data[0].y[1], 1)
        self.assertAlmostEqual(fig.data[1].y[0], 3 / 30)
        self.assertIn("preceding December days", html)
        self.assertIn("first 29 days", html)
        self.assertIn("zero means no submitted records", html)

    def test_full_year_is_not_labeled_partial(self):
        daily = analyze.obs_per_day(pd.DataFrame({
            "observed_on": pd.to_datetime(["2024-01-01", "2024-12-31"]),
        }))
        fig, html = self.chart(daily)
        self.assertEqual(fig.data[0].name, "2024")
        self.assertIn("2024: Jan 01–Dec 31", html)

    def test_single_day_remains_visible_and_empty_input_stays_empty(self):
        daily = analyze.obs_per_day(pd.DataFrame({
            "observed_on": pd.to_datetime(["2026-08-05"]),
        }))
        fig, _ = self.chart(daily)
        self.assertEqual(fig.data[0].mode, "markers")
        self.assertEqual(list(fig.data[0].y), [1])
        self.assertIn("No data yet", viz.per_day(daily.iloc[:0]))


if __name__ == "__main__":
    unittest.main()
