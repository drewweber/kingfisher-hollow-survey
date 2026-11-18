"""Publication-boundary tests for the aggregate-only bird route exporter."""

import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


EXPORTER = Path(__file__).resolve().parents[1] / "tools" / "export_bird_route_cells.py"


def inputs():
    grid = {
        "cell_size_m": 5,
        "grid_anchor_xy_m": [0, 0],
        "cells": [
            {"column": 0, "row": 0, "xmin_m": 0, "ymin_m": 0,
             "count": 2, "checklist_ids": ["PRIVATE-ID-A", "PRIVATE-ID-B"]},
            {"column": -1, "row": 1, "xmin_m": -5, "ymin_m": 5,
             "count": 1, "checklist_ids": ["PRIVATE-ID-A"]},
        ],
    }
    methods = {
        "projection": {
            "method": "Local spherical equirectangular",
            "projection_engine": "equirectangular", "units": "metres",
            "earth_radius_m": 6371008.8,
            "origin_longitude": -76.5, "origin_latitude": 42.0,
            "grid_anchor_xy_m": [0, 0],
        },
        "coverage": {
            "inventory_count": 4, "distinct_acquired_route_checklists": 2,
            "inventory_checklists_without_acquired_route": 2,
            "source_coverage": {
                "inventory_count": 4, "exported_route_count": 2,
                "unresolved_count": 2,
                "status_counts": {"exported": 2, "flagged_unresolved": 1,
                                  "missing_unresolved": 1},
            },
        },
        "summary": {"5": {"touched_cells": 2, "maximum_checklists_per_cell": 2}},
        "suppressed_gap_count": 1,
        "max_gap_m": 100,
        "route_sources": [{"checklist_id": "PRIVATE-ID-A", "source_files": ["PRIVATE-PATH"]}],
        "suppressed_gaps": [{"checklist_id": "PRIVATE-ID-B", "timestamp": "PRIVATE-TIME"}],
        "unexpected_private_data": "PRIVATE-EXTRA",
    }
    inventory = {
        "expected_count": 4, "displayed_count": 4,
        "captured_at": "2026-11-18T14:16:02.217Z",
        "checklists": [
            {"checklist_id": "PRIVATE-ID-A", "date_label": "18 Nov 2026 7:36 AM"},
            {"checklist_id": "PRIVATE-ID-B", "date_label": "1 Jul 2026 6:00 PM"},
            {"checklist_id": "PRIVATE-ID-C", "date_label": "1 Jul 2025 6:00 PM"},
            {"checklist_id": "PRIVATE-ID-D", "date_label": "30 Mar 2025 9:01 AM"},
        ],
        "source_url": "PRIVATE-URL",
    }
    return grid, methods, inventory


class BirdRouteExportTests(unittest.TestCase):
    def run_export(self, data=None, existing=None, extra_args=()):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, document in zip(("grid", "methods", "inventory"), data or inputs()):
                (root / f"{name}.json").write_text(json.dumps(document))
            output = root / "public.json"
            if existing is not None:
                output.write_text(existing)
            command = [sys.executable, str(EXPORTER)]
            for name in ("grid", "methods", "inventory"):
                command.extend((f"--{name}", str(root / f"{name}.json")))
            command.extend(("--output", str(output), *extra_args))
            result = subprocess.run(command, capture_output=True, text=True)
            return result, output.read_text() if output.exists() else None

    def test_export_is_an_explicit_public_allowlist(self):
        result, raw = self.run_export()
        self.assertEqual(result.returncode, 0, result.stderr)
        public = json.loads(raw)
        self.assertNotIn("PRIVATE", raw)
        self.assertEqual(set(public), {"metadata", "geojson"})
        self.assertEqual(public["metadata"], {
            "inventory_count": 4, "route_count": 2, "unresolved_count": 2,
            "flagged_unresolved_count": 1, "missing_unresolved_count": 1,
            "cell_size_m": 5, "snapshot_date": "2026-11-18",
            "date_start": "2025-03-30", "date_end": "2026-11-18",
            "suppressed_edge_count": 1, "max_count": 2, "cell_count": 2,
        })
        self.assertEqual(set(public["geojson"]), {"type", "features"})
        self.assertEqual(public["geojson"]["type"], "FeatureCollection")
        for index, feature in enumerate(public["geojson"]["features"], 1):
            self.assertEqual(set(feature), {"type", "id", "properties", "geometry"})
            self.assertEqual(feature["id"], f"cell-{index}")
            self.assertEqual(feature["type"], "Feature")
            self.assertEqual(set(feature["properties"]), {"route_count"})
            self.assertEqual(set(feature["geometry"]), {"type", "coordinates"})

    def test_inverse_projection_preserves_origin_and_five_metre_cells(self):
        result, raw = self.run_export()
        self.assertEqual(result.returncode, 0, result.stderr)
        features = json.loads(raw)["geojson"]["features"]
        origin_cell = next(f for f in features if f["properties"]["route_count"] == 2)
        ring = origin_cell["geometry"]["coordinates"][0]
        self.assertEqual(origin_cell["geometry"]["type"], "Polygon")
        self.assertEqual(len(ring), 5)
        self.assertEqual(ring[0], [-76.5, 42.0])
        self.assertEqual(ring[-1], ring[0])
        # Independent great-circle measurements catch swapped axes, missing
        # latitude correction, and a wrong radius or degrees/radians conversion.
        def metres(a, b):
            lat1, lat2 = math.radians(a[1]), math.radians(b[1])
            h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2
            return 12742017.6 * math.asin(math.sqrt(h))
        self.assertAlmostEqual(metres(ring[0], ring[1]), 5, delta=0.02)
        self.assertAlmostEqual(metres(ring[1], ring[2]), 5, delta=0.02)
        for feature in features:
            for point in feature["geometry"]["coordinates"][0]:
                self.assertTrue(all(round(value, 7) == value for value in point))

    def test_refuses_to_overwrite_an_existing_output(self):
        result, raw = self.run_export(existing="previous reviewed data")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(raw, "previous reviewed data")

    def test_rejects_malformed_inputs_without_creating_output(self):
        changes = [
            (0, lambda d: d.update(cell_size_m=10)),
            (0, lambda d: d["cells"][0].update(count=3)),
            (0, lambda d: d["cells"][0].update(count=True)),
            (0, lambda d: d["cells"][0].update(count=0)),
            (0, lambda d: d["cells"][0].update(xmin_m=1)),
            (0, lambda d: d["cells"][0].update(ymin_m=float("nan"))),
            (0, lambda d: d["cells"].append(copy.deepcopy(d["cells"][0]))),
            (1, lambda d: d["projection"].update(projection_engine="pyproj")),
            (1, lambda d: d["projection"].update(earth_radius_m=0)),
            (1, lambda d: d["projection"].update(origin_latitude=90)),
            (1, lambda d: d["summary"]["5"].update(touched_cells=3)),
            (1, lambda d: d.update(max_gap_m=500)),
            (1, lambda d: d["coverage"]["source_coverage"]["status_counts"].update(missing_unresolved=0)),
            (2, lambda d: d["checklists"][0].update(date_label="bad date")),
            (2, lambda d: d["checklists"][0].update(checklist_id="PRIVATE-ID-B")),
        ]
        for index, change in changes:
            with self.subTest(input_index=index, mutation=changes.index((index, change))):
                data = inputs()
                change(data[index])
                result, raw = self.run_export(data)
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(raw)


if __name__ == "__main__":
    unittest.main()
