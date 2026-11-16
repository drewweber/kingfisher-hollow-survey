import unittest
from unittest import mock

import pandas as pd

from src import viz


class ObservationMapTests(unittest.TestCase):
    def setUp(self):
        self.observations = pd.DataFrame(
            [
                {
                    "latitude": 42.123,
                    "longitude": -76.456,
                    "iconic_taxon": "Aves",
                    "common_name": "Wood Thrush",
                    "taxon_name": "Hylocichla mustelina",
                },
                {
                    "latitude": 42.124,
                    "longitude": -76.455,
                    "iconic_taxon": "Insecta",
                    "common_name": None,
                    "taxon_name": "Actias luna",
                },
            ]
        )

    def test_uses_maplibre_traces_and_layout(self):
        with mock.patch.object(viz, "_html", side_effect=lambda figure: figure):
            figure = viz.obs_map(self.observations)

        self.assertEqual(
            [trace.type for trace in figure.data],
            ["scattermap", "scattermap"],
        )
        self.assertEqual(figure.layout.map.style, "carto-positron")
        self.assertEqual(figure.layout.map.zoom, 15)
        self.assertAlmostEqual(figure.layout.map.center.lat, 42.1235)
        self.assertAlmostEqual(figure.layout.map.center.lon, -76.4555)
        self.assertEqual(list(figure.data[0].text), ["Wood Thrush"])
        self.assertEqual(list(figure.data[1].text), ["Actias luna"])
        self.assertNotIn("mapbox", figure.layout.to_plotly_json())

    def test_dark_map_keeps_the_dark_carto_basemap(self):
        with mock.patch.object(viz, "_html", side_effect=lambda figure: figure):
            figure = viz.obs_map(self.observations, dark=True)

        self.assertTrue(all(trace.type == "scattermap" for trace in figure.data))
        self.assertEqual(figure.layout.map.style, "carto-darkmatter")

    def map_figure(self, groups, dark=False):
        rows = [dict(self.observations.iloc[0], iconic_taxon=group) for group in groups]
        with mock.patch.object(viz, "_html", side_effect=lambda figure: figure):
            return viz.obs_map(pd.DataFrame(rows), dark=dark)

    def test_category_colors_are_distinct_and_stable_when_groups_change(self):
        groups = ["Arachnida", "Reptilia", "Plantae", "Amphibia", "Insecta",
                  "Mammalia", "Fungi", "Animalia", "Actinopterygii", "Mollusca",
                  "Aves", "Chromista", "Protozoa", "Other"]
        for dark in (False, True):
            with self.subTest(dark=dark):
                baseline = {t.name: t.marker.color for t in self.map_figure(groups, dark).data}
                self.assertEqual(len(set(baseline.values())), len(groups))
                for subset in (groups[::-1], groups[::2], ["Insecta"]):
                    actual = {t.name: t.marker.color for t in self.map_figure(subset, dark).data}
                    self.assertEqual(actual, {g: baseline[g] for g in subset})

    def test_unknown_groups_use_neutral_fallback_without_losing_labels(self):
        for dark in (False, True):
            figure = self.map_figure([None, "New taxon", "Plantae"], dark)
            other, unknown, plants = figure.data
            self.assertEqual(other.name, "Other")
            self.assertEqual(unknown.name, "New taxon")
            self.assertEqual(other.marker.color, unknown.marker.color)
            self.assertNotEqual(plants.marker.color, other.marker.color)
            self.assertTrue(figure.layout.showlegend)
            for trace in figure.data:
                self.assertIn(trace.name, trace.hovertemplate)
                self.assertEqual(list(trace.text), ["Wood Thrush"])

    def test_map_markers_contrast_with_light_and_dark_context(self):
        # Representative pale/dark neutral basemap surfaces, not every tile pixel.
        def luminance(color):
            channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                      for c in channels]
            return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

        for dark, background in ((False, "#dddddd"), (True, "#333333")):
            for trace in self.map_figure(list(viz.MAP_TAXON_COLORS), dark).data:
                levels = sorted([luminance(trace.marker.color), luminance(background)])
                contrast = (levels[1] + 0.05) / (levels[0] + 0.05)
                with self.subTest(dark=dark, group=trace.name):
                    self.assertGreaterEqual(contrast, 3)

    def test_empty_map_preserves_the_existing_fallback(self):
        empty = self.observations.assign(latitude=None, longitude=None)

        self.assertEqual(
            viz.obs_map(empty),
            "<p class='chart-empty'>No mappable (un-obscured) observations.</p>",
        )


if __name__ == "__main__":
    unittest.main()
