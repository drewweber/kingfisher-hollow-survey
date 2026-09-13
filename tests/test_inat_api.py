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


class FocusedObservationFetchTests(unittest.TestCase):
    def test_fetch_observations_deduplicates_and_preserves_requested_order(self):
        response = {
            "results": [
                {"id": 20, "photos": []},
                {"id": 10, "photos": []},
            ]
        }
        with patch.object(inat_api, "_get", return_value=response) as get:
            rows = inat_api.fetch_observations([10, 20, 10, "bad", -1])

        self.assertEqual([10, 20], [row["id"] for row in rows])
        self.assertEqual("observations/10,20", get.call_args.args[0])
        self.assertEqual(2, get.call_args.kwargs["per_page"])


class SexAnnotatedPhotoTests(unittest.TestCase):
    @staticmethod
    def _annotation(attribute_id, value_id):
        return {
            "controlled_attribute_id": attribute_id,
            "controlled_value_id": value_id,
        }

    @staticmethod
    def _photo(photo_id, width=1200, height=900):
        return {
            "id": photo_id,
            "url": f"https://example.test/{photo_id}/square.jpg",
            "attribution": "Example observer",
            "license_code": "cc-by",
            "original_dimensions": {"width": width, "height": height},
        }

    def test_fetches_reviewed_adult_male_and_female_photos_in_requested_order(self):
        adult = self._annotation(inat_api.LIFE_STAGE_ANNOTATION_ID, inat_api.ADULT_VALUE_ID)
        male = self._annotation(inat_api.SEX_ANNOTATION_ID, inat_api.SEX_VALUE_IDS["male"])
        female = self._annotation(inat_api.SEX_ANNOTATION_ID, inat_api.SEX_VALUE_IDS["female"])
        response = {"results": [
            {"id": 1, "annotations": [adult, male], "photos": [self._photo(101)]},
            {"id": 2, "annotations": [adult, female], "photos": [self._photo(201)]},
            {"id": 3, "annotations": [adult, male], "photos": [self._photo(102)]},
        ]}
        with patch.object(inat_api, "_get", return_value=response) as get:
            photos = inat_api.fetch_licensed_sex_photos(
                55, preferred_photo_ids={"male": 102, "female": 201}
            )

        self.assertEqual([102, 201], [photo["id"] for photo in photos])
        self.assertEqual(["male", "female"], [photo["sex"] for photo in photos])
        self.assertTrue(all(photo["life_stage"] == "adult" for photo in photos))
        self.assertTrue(all(photo["sex_evidence"] for photo in photos))
        self.assertEqual("observations", get.call_args.args[0])
        self.assertEqual(9, get.call_args.kwargs["term_id"])
        self.assertEqual("11,10", get.call_args.kwargs["term_value_id"])
        self.assertEqual(200, get.call_args.kwargs["per_page"])

    def test_rejects_nonadult_and_low_quality_sex_photos(self):
        adult = self._annotation(inat_api.LIFE_STAGE_ANNOTATION_ID, inat_api.ADULT_VALUE_ID)
        nymph = self._annotation(inat_api.LIFE_STAGE_ANNOTATION_ID, 5)
        female = self._annotation(inat_api.SEX_ANNOTATION_ID, inat_api.SEX_VALUE_IDS["female"])
        response = {"results": [
            {"id": 1, "annotations": [nymph, female], "photos": [self._photo(201)]},
            {"id": 2, "annotations": [adult, female], "photos": [self._photo(202, 300, 300)]},
            {"id": 3, "annotations": [adult, female], "photos": [self._photo(203, 3000, 600)]},
            {"id": 4, "annotations": [adult, female], "photos": [self._photo(204)]},
        ]}
        with patch.object(inat_api, "_get", return_value=response):
            photos = inat_api.fetch_licensed_sex_photos(55, sexes=("female",))

        self.assertEqual([204], [photo["id"] for photo in photos])


if __name__ == "__main__":
    unittest.main()
