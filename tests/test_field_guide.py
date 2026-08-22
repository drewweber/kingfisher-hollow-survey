import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import field_guide  # noqa: E402
from field_guidance import (  # noqa: E402
    build_guidance,
    guidance_profile,
    survey_period_profile,
)
from field_identification import (  # noqa: E402
    NO_NAMED_COMPARISON_NOTES,
    PAIR_PROFILES,
    curated_peer_names,
    has_curated_comparison_disposition,
)


class FieldGuidanceTests(unittest.TestCase):
    def test_every_group_has_complete_fallback_guidance(self):
        for group in ("moths", "butterflies", "odonates"):
            guidance = build_guidance(
                group,
                "",
                "Test species",
                "Jun-Sep",
                12,
                [],
            )
            for key in (
                "survey_periods", "habitat_tags", "method_tags", "finding_help", "id_help",
                "id_traits", "photo_checklist",
            ):
                self.assertTrue(guidance[key], f"{group} has no {key}")
            self.assertTrue(guidance["survey_period_note"])
            self.assertTrue(guidance["target_reason"])
            self.assertTrue(guidance["id_limitations"])
            self.assertTrue(guidance["comparison_note"])
            self.assertTrue(guidance["id_traits"][0]["label"])
            self.assertEqual([], guidance["lookalikes"])

    def test_curated_comparison_names_specific_visible_differences(self):
        guidance = build_guidance(
            "moths",
            "Sphingidae",
            "Hummingbird Clearwing",
            "Jun-Aug",
            12,
            [{
                "taxon_id": 2,
                "common_name": "Snowberry Clearwing",
                "scientific_name": "Hemaris diffinis",
            }],
            "Hemaris thysbe",
        )
        comparison = guidance["lookalikes"][0]
        self.assertEqual("conditional", comparison["identifiability"])
        self.assertEqual("Hemaris sp.", comparison["report_as"])
        self.assertIn("Pale cream", comparison["differences"][0]["target"])
        self.assertIn("Black legs", comparison["differences"][0]["peer"])

    def test_unidentifiable_pair_explicitly_stops_at_higher_taxon(self):
        guidance = build_guidance(
            "moths",
            "Tortricidae",
            "Raspberry Leafroller Moth",
            "Jun-Aug",
            12,
            [{
                "taxon_id": 2,
                "common_name": "Diamondback Epinotia Moth",
                "scientific_name": "Epinotia lindana",
            }],
            "Epinotia medioviridana",
        )
        comparison = guidance["lookalikes"][0]
        self.assertEqual("not_field", comparison["identifiability"])
        self.assertEqual([], comparison["differences"])
        self.assertEqual("Epinotia sp.", comparison["report_as"])
        self.assertIn("ordinary field photographs", comparison["decision"].casefold())

    def test_bluet_comparison_requires_diagnostic_terminal_structures(self):
        guidance = build_guidance(
            "odonates",
            "Coenagrionidae",
            "Azure Bluet",
            "Jun-Aug",
            12,
            [{
                "taxon_id": 2,
                "common_name": "Familiar Bluet",
                "scientific_name": "Enallagma civile",
            }],
            "Enallagma aspersum",
        )
        comparison = guidance["lookalikes"][0]
        self.assertEqual("not_field", comparison["identifiability"])
        self.assertEqual([], comparison["differences"])
        self.assertEqual("Enallagma sp.", comparison["report_as"])
        self.assertIn("terminal appendages", comparison["decision"])
        self.assertIn("mesostigmal plates", comparison["decision"])

    def test_arbitrary_family_members_are_not_presented_as_lookalikes(self):
        guidance = build_guidance(
            "moths",
            "Sphingidae",
            "Pandorus Sphinx",
            "Jun-Aug",
            12,
            [{
                "taxon_id": 2,
                "common_name": "Waved Sphinx",
                "scientific_name": "Ceratomia undulosa",
            }],
            "Eumorpha pandorus",
        )
        self.assertEqual([], guidance["lookalikes"])
        self.assertIn("No named confusion species", guidance["comparison_note"])

    def test_every_previously_blank_current_target_has_a_confusion_disposition(self):
        previously_blank = {
            "Catocala cara", "Thyris maculata", "Eumorpha pandorus", "Oreta rosea",
            "Hypena bijugalis", "Catocala retecta", "Xanthorhoe labradorensis",
            "Amorpha juglandis", "Eustixia pupula", "Clemensia umbrata",
            "Eichlinia cucurbitae", "Euphydryas phaeton", "Thymelicus lineola",
            "Limochores mystic", "Aglais milberti", "Lethe eurydice",
            "Papilio canadensis", "Lycaena hypophlaeas", "Argynnis atlantis",
            "Pieris virginiensis", "Cupido comyntas", "Perithemis tenera", "Ladona julia",
            "Hetaerina americana", "Phanogomphus exilis", "Amphiagrion saucium",
            "Tachopteryx thoreyi", "Leucorrhinia glacialis", "Lestes eurinus",
        }
        for scientific_name in previously_blank:
            has_named_comparison = bool(curated_peer_names(scientific_name))
            has_explicit_note = scientific_name in NO_NAMED_COMPARISON_NOTES
            self.assertTrue(
                has_named_comparison or has_explicit_note,
                f"{scientific_name} still has no confusion disposition",
            )

    def test_nonregional_documented_peer_is_retained_as_a_comparison(self):
        peers = {
            "moths": field_guide.pd.DataFrame([{
                "taxon_id": 1,
                "taxon_name": "Ceratomia undulosa",
                "common_name": "Waved Sphinx",
            }]),
        }
        comparisons = field_guide._lookalikes(
            "moths", "Eumorpha pandorus", "Sphingidae", peers
        )
        self.assertEqual(122356, comparisons[0]["taxon_id"])
        self.assertEqual("Eumorpha achemon", comparisons[0]["scientific_name"])

    def test_rotating_least_skipper_target_has_a_named_confusion(self):
        self.assertIn("Thymelicus lineola", curated_peer_names("Ancyloxypha numitor"))

    def test_expanded_moth_targets_have_specific_confusion_dispositions(self):
        added_targets = {
            "Acleris macdunnoughi", "Acronicta afflicta", "Ascalapha odorata",
            "Cameraria caryaefoliella", "Catocala ilia", "Choreutis pariana",
            "Coptotriche aenea", "Coptotriche castaneaeella", "Ectoedemia platanella",
            "Euxoa bostoniensis", "Glaucolepis saccharella", "Marimatha nigrofimbria",
            "Meropleon diversicolor", "Papaipema pterisii", "Parectopa robiniella",
            "Phyllonorycter maestingella", "Stigmella caryaefoliella",
            "Stigmella rosaefoliella",
        }
        for scientific_name in added_targets:
            self.assertTrue(has_curated_comparison_disposition(scientific_name))

    def test_moth_target_window_includes_current_and_next_two_months(self):
        self.assertEqual([8, 9, 10], field_guide._moth_target_months(date(2026, 8, 16)))
        self.assertEqual([11, 12, 1], field_guide._moth_target_months(date(2026, 11, 30)))

    def test_moth_candidate_frame_prefers_seasonal_and_filters_generic_gaps(self):
        seasonal = field_guide.pd.DataFrame([
            {"taxon_id": 1, "taxon_name": "Hemaris thysbe", "ref_count": 2},
            {"taxon_id": 2, "taxon_name": "Unsupported example", "ref_count": 4},
        ])
        annual = field_guide.pd.DataFrame([
            {"taxon_id": 1, "taxon_name": "Hemaris thysbe", "ref_count": 200},
            {"taxon_id": 3, "taxon_name": "Eumorpha pandorus", "ref_count": 100},
        ])
        with patch.object(
            field_guide.analyze,
            "moth_county_gap",
            side_effect=[{"missing": seasonal}, {"missing": annual}],
        ):
            selected = field_guide._moth_candidate_frame(field_guide.pd.DataFrame(), [8, 9, 10])
        self.assertEqual(["Hemaris thysbe", "Eumorpha pandorus"], selected["taxon_name"].tolist())
        self.assertEqual([1, 0], selected["_seasonal_priority"].tolist())

    def test_every_curated_pair_has_a_field_decision_and_valid_fallback(self):
        pair_keys = [frozenset(profile["taxa"]) for profile in PAIR_PROFILES]
        self.assertEqual(len(pair_keys), len(set(pair_keys)))
        for profile in PAIR_PROFILES:
            self.assertIn(profile["status"], {"field", "conditional", "not_field"})
            self.assertTrue(profile["decision"])
            if profile["status"] == "not_field":
                self.assertFalse(profile["differences"])
                self.assertTrue(profile["report_as"])
            else:
                self.assertTrue(profile["differences"])
            if profile["status"] == "conditional":
                self.assertTrue(profile["report_as"])
            self.assertEqual(2, len(profile["taxa"]))
            for taxon in profile["taxa"]:
                self.assertIn(
                    next(name for name in profile["taxa"] if name != taxon),
                    curated_peer_names(taxon),
                )

    def test_curated_comparisons_do_not_contain_generic_templates(self):
        forbidden = (
            "compare the complete",
            "show the entire",
            "full character set",
            "rather than using color alone",
            "check these traits",
        )
        for profile in PAIR_PROFILES:
            text = " ".join([
                profile["decision"],
                *[
                    " ".join((difference["feature"], difference["first"], difference["second"]))
                    for difference in profile["differences"]
                ],
            ]).casefold()
            for phrase in forbidden:
                self.assertNotIn(phrase, text)

    def test_difficult_families_keep_conservative_limitations(self):
        tortricid = guidance_profile("moths", "Tortricidae", "Leafroller Moth")
        bluet = guidance_profile("odonates", "Coenagrionidae", "Azure Bluet")
        skipper = guidance_profile("butterflies", "Hesperiidae", "Dun Skipper")
        self.assertIn("genus", tortricid["limitation"].casefold())
        self.assertIn("terminal", bluet["limitation"].casefold())
        self.assertIn("species-group", skipper["limitation"].casefold())

    def test_survey_periods_separate_adult_activity_and_named_day_methods(self):
        nocturnal = survey_period_profile(
            "moths", "Noctuidae", "Primrose Moth", "Schinia florida",
            ["UV light", "host search"],
        )
        day_flying = survey_period_profile(
            "moths", "Sphingidae", "Hummingbird Clearwing", "Hemaris thysbe",
            ["day watch", "UV light"],
        )
        searchable_both = survey_period_profile(
            "moths", "Tortricidae", "Raspberry Leafroller Moth",
            "Epinotia medioviridana", ["rolled-leaf search", "UV light"],
        )
        darner = survey_period_profile(
            "odonates", "Aeshnidae", "Shadow Darner", "Aeshna umbrosa",
            ["patrol watch", "evening flight"],
        )

        self.assertEqual(["night"], nocturnal["survey_periods"])
        self.assertEqual(["day"], day_flying["survey_periods"])
        self.assertEqual(["day", "night"], searchable_both["survey_periods"])
        self.assertEqual(["day", "night"], darner["survey_periods"])
        self.assertEqual(
            ["day"],
            survey_period_profile("butterflies", "Nymphalidae")["survey_periods"],
        )
        clearwing_guidance = build_guidance(
            "moths", "Sphingidae", "Hummingbird Clearwing", "Jun-Aug", 12, [],
            "Hemaris thysbe",
        )
        self.assertIn("day watch", clearwing_guidance["method_tags"])
        self.assertNotIn("UV light", clearwing_guidance["method_tags"])
        self.assertNotIn("dusk", " ".join(clearwing_guidance["finding_help"]).casefold())


class FieldGuideReleaseTests(unittest.TestCase):
    def test_inactive_taxon_uses_accepted_id_for_photo_search(self):
        normalized = field_guide._normalize_taxon({
            "id": 122381,
            "is_active": False,
            "current_synonymous_taxon_ids": [58555],
            "ancestors": [],
            "default_photo": None,
        })
        self.assertEqual(122381, normalized["taxon_id"])
        self.assertEqual(58555, normalized["photo_search_taxon_id"])

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
            "survey_periods": ["night"],
            "survey_period_note": "Search after dusk.",
            "comparison_note": "No close comparison is vetted.",
            "habitat_tags": ["forest edge"],
            "method_tags": ["UV light"],
            "finding_help": ["Look on warm nights."],
            "id_help": ["Record the complete wing pattern."],
            "id_traits": [{"label": "Forewing", "detail": "Record the complete wing pattern."}],
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

    def test_published_reference_images_are_deduplicated_by_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "images").mkdir()
            first = root / "first-source.jpg"
            duplicate = root / "duplicate-source.jpg"
            distinct = root / "distinct-source.jpg"
            first.write_bytes(b"same reference image")
            duplicate.write_bytes(b"same reference image")
            distinct.write_bytes(b"different reference image")

            first_path, first_output = field_guide._publish_image(first, root)
            duplicate_path, duplicate_output = field_guide._publish_image(duplicate, root)
            distinct_path, distinct_output = field_guide._publish_image(distinct, root)

            self.assertEqual(first_path, duplicate_path)
            self.assertEqual(first_output, duplicate_output)
            self.assertNotEqual(first_path, distinct_path)
            self.assertTrue(first_output.is_file())
            self.assertTrue(distinct_output.is_file())
            self.assertEqual(2, len(list((root / "images").iterdir())))

    def test_offline_manifest_hashes_exact_asset_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_bytes(b"app shell")
            (root / "app.js").write_bytes(b"application code")

            manifest = field_guide._offline_asset_manifest(
                root, ["./", "./index.html", "./app.js"]
            )

            self.assertEqual(
                ["./", "./index.html", "./app.js"],
                [row["path"] for row in manifest],
            )
            self.assertEqual(manifest[0]["sha256"], manifest[1]["sha256"])
            self.assertNotEqual(manifest[1]["sha256"], manifest[2]["sha256"])
            self.assertTrue(all(len(row["sha256"]) == 64 for row in manifest))

    def test_offline_cache_version_changes_with_final_asset_bytes(self):
        first = [{"path": "./app.js", "sha256": "a" * 64}]
        changed = [{"path": "./app.js", "sha256": "b" * 64}]

        self.assertNotEqual(
            field_guide._offline_cache_version(first),
            field_guide._offline_cache_version(changed),
        )

    def test_service_worker_is_path_scoped_by_request_guard(self):
        worker = (ROOT / "field-guide" / "service-worker.js").read_text(encoding="utf-8")
        self.assertIn("self.registration.scope", worker)
        self.assertIn("requestUrl.pathname.startsWith(scopeUrl.pathname)", worker)
        self.assertNotIn("/api/update", worker)

    def test_new_release_reuses_only_exact_content_addressed_assets(self):
        worker = (ROOT / "field-guide" / "service-worker.js").read_text(encoding="utf-8")
        cache_one = worker.split("async function cacheOne", 1)[1].split(
            "async function prepareOffline", 1
        )[0]
        self.assertIn('url.searchParams.set("v", asset.sha256)', worker)
        self.assertIn("const reusable = await caches.match(key)", cache_one)
        self.assertIn("await cache.put(key, reusable)", cache_one)
        self.assertIn('fetch(url, { cache: "no-cache" })', cache_one)

    def test_runtime_reads_only_the_current_versioned_cache(self):
        worker = (ROOT / "field-guide" / "service-worker.js").read_text(encoding="utf-8")
        fetch_handler = worker.split('self.addEventListener("fetch"', 1)[1]
        self.assertIn("const cache = await caches.open(CACHE_NAME)", fetch_handler)
        self.assertIn("await cache.match(event.request", fetch_handler)
        self.assertNotIn("await caches.match(event.request", fetch_handler)
        self.assertIn(
            'cache.match(absolute("./index.html"), { ignoreSearch: true })',
            fetch_handler,
        )

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
        self.assertIn("Traits to check", app)
        self.assertIn("Visible differences", app)
        self.assertIn("Field decision", app)
        self.assertIn("Potential confusions", app)
        self.assertIn("comparisonNote", app)
        self.assertIn("ID reference", app)
        self.assertIn("comparison-difference-list", app)
        self.assertNotIn("Check these traits against", app)
        self.assertNotIn("lookalike.traits", app)
        self.assertNotIn("lookalike.distinction", app)

    def test_field_app_exposes_local_moth_flight_signals(self):
        app = (ROOT / "field-guide" / "app" / "app.js").read_text(encoding="utf-8")
        markup = (ROOT / "field-guide" / "app" / "index.html").read_text(encoding="utf-8")
        self.assertIn("normalizeLocalSignal", app)
        self.assertIn("Why it may be flying now", app)
        self.assertIn("appendLocalSignal", app)
        self.assertIn('id="local-signal-filter"', markup)

    def test_field_app_exposes_day_and_night_survey_modes(self):
        app = (ROOT / "field-guide" / "app" / "app.js").read_text(encoding="utf-8")
        markup = (ROOT / "field-guide" / "app" / "index.html").read_text(encoding="utf-8")
        self.assertIn('name="period" value="day"', markup)
        self.assertIn('name="period" value="night"', markup)
        self.assertIn("target.surveyPeriods.includes(state.period)", app)
        self.assertIn("When to search", app)
        self.assertIn("surveyPeriodNote", app)

    def test_skip_link_is_hidden_until_focus_and_targets_a_focusable_heading(self):
        markup = (ROOT / "field-guide" / "app" / "index.html").read_text(encoding="utf-8")
        styles = (ROOT / "field-guide" / "app" / "styles.css").read_text(encoding="utf-8")
        self.assertIn('class="skip-link" href="#results-heading"', markup)
        self.assertIn('id="results-heading" tabindex="-1"', markup)
        self.assertIn(".skip-link:not(:focus)", styles)
        self.assertIn("clip-path: inset(50%)", styles)

    def test_field_guide_targets_exactly_forty_moths(self):
        self.assertEqual(40, field_guide.MOTH_TARGET_LIMIT)

    def test_night_mode_uses_a_persisted_low_light_theme(self):
        app = (ROOT / "field-guide" / "app" / "app.js").read_text(encoding="utf-8")
        markup = (ROOT / "field-guide" / "app" / "index.html").read_text(encoding="utf-8")
        styles = (ROOT / "field-guide" / "app" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("applySurveyPeriodTheme", app)
        self.assertIn('document.documentElement.dataset.surveyPeriod = period', app)
        self.assertIn('localStorage.getItem("kh-field-survey-period") === "night"', markup)
        self.assertLess(
            markup.index('localStorage.getItem("kh-field-survey-period")'),
            markup.index('<link rel="stylesheet"'),
        )
        self.assertIn(':root[data-survey-period="night"]', styles)
        self.assertIn("color-scheme: dark", styles)
        self.assertIn("filter: brightness(0.46)", styles)
        self.assertIn("filter: brightness(0.66)", styles)

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
