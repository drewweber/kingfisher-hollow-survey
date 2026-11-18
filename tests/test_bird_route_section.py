"""Bird route coverage stays usable and follows the supplied snapshot."""

import re
import unittest
from html import unescape
from unittest import mock

import pandas as pd

import report


class BirdRouteSectionTests(unittest.TestCase):
    def setUp(self):
        # Synthetic coordinates and deliberately different totals catch stale
        # snapshot numbers without using any private route records in tests.
        self.routes = {
            "metadata": {
                "inventory_count": 4,
                "route_count": 3,
                "unresolved_count": 1,
                "flagged_unresolved_count": 1,
                "missing_unresolved_count": 0,
                "cell_size_m": 5,
                "snapshot_date": "2026-01-03",
                "date_start": "2026-01-01",
                "date_end": "2026-01-03",
                "suppressed_edge_count": 2,
                "max_count": 3,
                "cell_count": 2,
            },
            "geojson": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "cell-0",
                        "properties": {"route_count": 3},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[0, 0], [0.00005, 0],
                                             [0.00005, 0.00005], [0, 0.00005], [0, 0]]],
                        },
                    },
                    {
                        "type": "Feature",
                        "id": "cell-1",
                        "properties": {"route_count": 1},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[0.00005, 0], [0.0001, 0],
                                             [0.0001, 0.00005], [0.00005, 0.00005], [0.00005, 0]]],
                        },
                    },
                ],
            },
        }

    def render_birds(self):
        with mock.patch.object(report.analyze, "load_birds", return_value=pd.DataFrame()), \
             mock.patch.object(report.bird_routes, "load", return_value=self.routes):
            return report.birds_view()

    def test_route_navigation_reaches_section_before_recent_records(self):
        html = self.render_birds()
        self.assertTrue('id="bird-route-use"' in html, "Bird route section is missing")
        self.assertLess(html.index('id="birds"'), html.index('id="bird-route-use"'))
        self.assertLess(html.index('id="bird-route-use"'), html.index('id="bird-recent"'))
        self.assertIn('href="#bird-route-use"', report.nav("birds"))

    def test_route_coverage_uses_snapshot_even_without_a_bird_life_list(self):
        html = self.render_birds()
        self.assertTrue('id="bird-route-use"' in html, "Bird route section is missing")
        section = html.split('id="bird-route-use"', 1)[1].split('</section>', 1)[0]
        text = " ".join(unescape(re.sub(r"<[^>]+>", " ", section)).split())
        self.assertIn("3 of 4", text)
        self.assertIn("75.0%", text)
        self.assertIn("Jan 1, 2026", text)
        self.assertIn("Jan 3, 2026", text)
        self.assertIn("1 unresolved", text)
        self.assertNotIn("628", text)
        self.assertNotIn("91.5%", text)

    def test_chart_has_visible_description_and_native_method_disclosure(self):
        html = self.render_birds()
        self.assertTrue('id="bird-route-use"' in html, "Bird route section is missing")
        section = html.split('id="bird-route-use"', 1)[1].split('</section>', 1)[0]
        self.assertRegex(section, r"<figure\b[\s\S]*data-bird-route-map[\s\S]*<figcaption\b")
        self.assertRegex(section, r"<details\b[\s\S]*<summary\b")
        summary = re.search(r"<summary\b[^>]*>([\s\S]*?)</summary>", section).group(1)
        self.assertNotRegex(summary, r"<h[1-6]\b")

    def test_only_bird_page_loads_native_route_map_script(self):
        script = report.scripts("birds")
        self.assertRegex(script, r'<script\b[^>]*src="/assets/bird-route-map\.js[^>]*\bdefer\b')
        self.assertNotIn("window.Plotly.newPlot", script)
        self.assertNotIn("window.__plotlyQueue", report.head({"species": 1}, 0, mode="birds"))
        for mode in report.VIEW_CONFIG:
            if mode != "birds":
                with self.subTest(mode=mode):
                    self.assertNotIn("/assets/bird-route-map.js", report.scripts(mode))


if __name__ == "__main__":
    unittest.main()
