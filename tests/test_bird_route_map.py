import json
from pathlib import Path
import tempfile
import unittest
from src import bird_routes


def sample():
    return {
        'metadata': {
            'inventory_count': 4, 'route_count': 3, 'unresolved_count': 1,
            'flagged_unresolved_count': 1, 'missing_unresolved_count': 0,
            'cell_size_m': 5, 'snapshot_date': '2026-11-18',
            'date_start': '2025-03-30', 'date_end': '2026-11-18',
            'suppressed_edge_count': 0, 'max_count': 3, 'cell_count': 1,
        },
        'geojson': {'type': 'FeatureCollection', 'features': [{
            'type': 'Feature', 'id': 'cell-0', 'properties': {'route_count': 3},
            'geometry': {'type': 'Polygon', 'coordinates': [[
                [-76.0, 42.0], [-75.99994, 42.0], [-75.99994, 42.000045],
                [-76.0, 42.000045], [-76.0, 42.0],
            ]]},
        }]},
    }


class PublicRouteMapTests(unittest.TestCase):
    def test_log_legend_labels_raw_counts_at_their_transformed_positions(self):
        ticks = bird_routes.legend_ticks(468)
        self.assertEqual([value for value, position in ticks], [1, 5, 20, 100, 468])
        for (_, position), expected in zip(ticks, [0, 0.262, 0.487, 0.749, 1]):
            self.assertAlmostEqual(position, expected, delta=0.001)
        self.assertEqual(bird_routes.legend_ticks(1), [(1, 0)])
        self.assertEqual([value for value, position in bird_routes.legend_ticks(3)], [1, 2, 3])

    def test_build_rejects_private_membership_and_unknown_metadata(self):
        for target, key, value in [('feature', 'checklist_ids', ['S12345']),
                                   ('metadata', 'source_files', ['/private/raw.kml'])]:
            data = sample()
            if target == 'feature':
                data['geojson']['features'][0]['properties'][key] = value
            else:
                data['metadata'][key] = value
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'cells.json'
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    bird_routes.load(path)

    def test_invalid_counts_fail_before_chart_serialization(self):
        for count in [0, 4, True, 1.5]:
            data = sample()
            data['geojson']['features'][0]['properties']['route_count'] = count
            with self.subTest(count=count), self.assertRaises(ValueError):
                bird_routes.validate(data)

    def test_public_cells_render_at_their_geographic_location_with_true_counts(self):
        data = sample()
        html = bird_routes.map_html(data)
        payload = html.split('data-route-cells>', 1)[1].split('</script>', 1)[0]
        self.assertEqual(data, json.loads(payload))
        self.assertIn('data-route-map-svg', html)
        self.assertIn('type="checkbox" data-map-overlay checked', html)
        self.assertIn('aria-label="Zoom in"', html)
        self.assertIn('tabindex="0"', html)
        self.assertNotIn('Plotly', html)


if __name__ == '__main__':
    unittest.main()
