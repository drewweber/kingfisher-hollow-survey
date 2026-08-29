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

    def test_empty_map_preserves_the_existing_fallback(self):
        empty = self.observations.assign(latitude=None, longitude=None)

        self.assertEqual(
            viz.obs_map(empty),
            "<p class='chart-empty'>No mappable (un-obscured) observations.</p>",
        )


if __name__ == "__main__":
    unittest.main()
