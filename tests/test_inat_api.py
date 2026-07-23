import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import inat_api  # noqa: E402


class UpdatedObservationIteratorTests(unittest.TestCase):
    def test_iter_updated_since_pages_in_update_order(self):
        pages = [
            {"results": [{"id": 1}, {"id": 2}]},
            {"results": [{"id": 3}]},
        ]
        with patch.object(inat_api, "PER_PAGE", 2), patch.object(
            inat_api, "_get", side_effect=pages
        ) as get:
            rows = list(inat_api.iter_updated_since(
                "2026-07-20T12:00:00Z", project_id=249580
            ))

        self.assertEqual([1, 2, 3], [row["id"] for row in rows])
        first = get.call_args_list[0].kwargs
        second = get.call_args_list[1].kwargs
        self.assertEqual("observations", get.call_args_list[0].args[0])
        self.assertEqual("updated_at", first["order_by"])
        self.assertEqual("asc", first["order"])
        self.assertEqual("2026-07-20T12:00:00Z", first["updated_since"])
        self.assertEqual(1, first["page"])
        self.assertEqual(2, second["page"])


if __name__ == "__main__":
    unittest.main()
