import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import field_guide  # noqa: E402
from field_guidance import build_guidance, guidance_profile  # noqa: E402


class FieldGuidanceTests(unittest.TestCase):
    def test_every_group_has_complete_fallback_guidance(self):
        for group in ("moths", "butterflies", "odonates"):
            guidance = build_guidance(
                group,
                "",
                "Test species",
                "Jun-Sep",
                12,
                [{"taxon_id": 2, "common_name": "Nearby congener", "scientific_name": "Testa altera"}],
            )
            for key in (
                "habitat_tags", "method_tags", "finding_help", "id_help",
                "photo_checklist", "lookalikes",
            ):
                self.assertTrue(guidance[key], f"{group} has no {key}")
            self.assertTrue(guidance["target_reason"])
            self.assertTrue(guidance["id_limitations"])
            self.assertIn("Nearby congener", guidance["lookalikes"][0]["name"])
            self.assertEqual(2, guidance["lookalikes"][0]["taxon_id"])

    def test_difficult_families_keep_conservative_limitations(self):
        tortricid = guidance_profile("moths", "Tortricidae", "Leafroller Moth")
        bluet = guidance_profile("odonates", "Coenagrionidae", "Azure Bluet")
        skipper = guidance_profile("butterflies", "Hesperiidae", "Dun Skipper")
        self.assertIn("genus", tortricid["limitation"].casefold())
        self.assertIn("terminal", bluet["limitation"].casefold())
        self.assertIn("species-group", skipper["limitation"].casefold())


class FieldGuideReleaseTests(unittest.TestCase):
    def _target(self, image_path="images/1.jpg", license_code="cc-by"):
        images = []
        for index in (1, 2):
            path = image_path.replace("1.jpg", f"{index}.jpg")
            images.append({
                "image": path,
                "image_alt": f"Example reference {index}",
                "image_attribution": "Example photographer",
                "image_license": "CC BY",
                "image_license_code": license_code,
                "image_source_url": f"https://www.inaturalist.org/photos/{index}",
            })
        return {
            "id": 1,
            "common_name": "Example Moth",
            "scientific_name": "Exempla motha",
            "season_label": "Jun-Aug",
            "target_reason": "Nearby and not recorded here.",
            "id_limitations": "Keep provisional when marks are missing.",
            "image": image_path,
            "image_attribution": "Example photographer",
            "image_license": "CC BY",
            "image_license_code": license_code,
            "image_source_url": "https://www.inaturalist.org/photos/1",
            "images": images,
            "active_months": [6, 7, 8],
            "habitat_tags": ["forest edge"],
            "method_tags": ["UV light"],
            "finding_help": ["Look on warm nights."],
            "id_help": ["Record the complete wing pattern."],
            "photo_checklist": ["Square dorsal frame."],
        }

    def test_release_validator_accepts_complete_local_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            images = root / "images"
            images.mkdir(parents=True)
            (images / "1.jpg").write_bytes(b"reference image")
            (images / "2.jpg").write_bytes(b"reference image")
            field_guide._validate_targets([self._target()], root)

    def test_release_validator_rejects_unlicensed_media(self):
        with self.assertRaisesRegex(ValueError, "unapproved image license"):
            field_guide._validate_targets([self._target(license_code="")])

    def test_generated_icons_are_valid_png_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            icon = Path(temporary) / "icon.png"
            field_guide._write_png(icon, 64)
            self.assertTrue(icon.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertGreater(icon.stat().st_size, 100)

    def test_service_worker_is_path_scoped_by_request_guard(self):
        worker = (ROOT / "field-guide" / "service-worker.js").read_text(encoding="utf-8")
        self.assertIn("self.registration.scope", worker)
        self.assertIn("requestUrl.pathname.startsWith(scopeUrl.pathname)", worker)
        self.assertNotIn("/api/update", worker)

    def test_new_release_does_not_copy_stale_assets_between_caches(self):
        worker = (ROOT / "field-guide" / "service-worker.js").read_text(encoding="utf-8")
        cache_one = worker.split("async function cacheOne", 1)[1].split(
            "async function prepareOffline", 1
        )[0]
        self.assertNotIn("caches.match", cache_one)
        self.assertIn('fetch(url, { cache: "no-cache" })', cache_one)

    def test_runtime_reads_only_the_current_versioned_cache(self):
        worker = (ROOT / "field-guide" / "service-worker.js").read_text(encoding="utf-8")
        fetch_handler = worker.split('self.addEventListener("fetch"', 1)[1]
        self.assertIn("const cache = await caches.open(CACHE_NAME)", fetch_handler)
        self.assertIn("await cache.match(event.request", fetch_handler)
        self.assertNotIn("await caches.match(event.request", fetch_handler)

    def test_online_launch_checks_for_a_new_release_without_http_cache(self):
        app = (ROOT / "field-guide" / "app" / "app.js").read_text(encoding="utf-8")
        self.assertIn('updateViaCache: "none"', app)
        self.assertIn("await state.registration.update()", app)

    def test_field_app_requires_two_reference_images_and_illustrates_comparisons(self):
        app = (ROOT / "field-guide" / "app" / "app.js").read_text(encoding="utf-8")
        builder = (ROOT / "src" / "field_guide.py").read_text(encoding="utf-8")
        self.assertIn("TARGET_IMAGE_COUNT = 2", builder)
        self.assertIn("comparison-photo-grid", app)
        self.assertIn("createReferenceGallery", app)

    def test_new_release_refreshes_the_visible_target_list(self):
        app = (ROOT / "field-guide" / "app" / "app.js").read_text(encoding="utf-8")
        controller_change = app.split(
            'navigator.serviceWorker.addEventListener("controllerchange"', 1
        )[1].split("try {", 1)[0]
        self.assertIn("loadTargets()", controller_change)
        self.assertIn("verifyOfflineCopy()", controller_change)

        worker = (ROOT / "field-guide" / "service-worker.js").read_text(encoding="utf-8")
        activate = worker.split('self.addEventListener("activate"', 1)[1].split(
            'self.addEventListener("message"', 1
        )[0]
        self.assertIn("await self.clients.claim()", activate)
        self.assertIn("client.navigate(client.url).catch", activate)
        self.assertNotIn("await client.navigate(client.url)", activate)


if __name__ == "__main__":
    unittest.main()
