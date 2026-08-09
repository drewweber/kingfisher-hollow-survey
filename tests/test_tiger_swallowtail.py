import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import db  # noqa: E402
import tiger_swallowtail as tiger  # noqa: E402


def observation(
    observation_id=101,
    taxon_id=tiger.MIDSUMMER_TAXON_ID,
    observed_on="2026-07-23",
    ancestor_ids=None,
    photos=None,
):
    names = {
        tiger.EASTERN_TAXON_ID: (
            "Papilio glaucus", "Eastern Tiger Swallowtail", "species"
        ),
        tiger.MIDSUMMER_TAXON_ID: (
            "Papilio solstitius", "Midsummer Tiger Swallowtail", "species"
        ),
        tiger.TIGER_COMPLEX_TAXON_ID: (
            "Papilio glaucus", "Eastern Tiger Swallowtail Complex", "complex"
        ),
    }
    scientific, common, rank = names.get(
        taxon_id, ("Example taxon", "Example taxon", "subspecies")
    )
    taxon_ancestors = (
        ancestor_ids if ancestor_ids is not None
        else [47225, tiger.TIGER_COMPLEX_TAXON_ID, taxon_id]
    )
    return {
        "id": observation_id,
        "uuid": f"uuid-{observation_id}",
        "observed_on": observed_on,
        "time_observed_at": f"{observed_on}T13:00:00-04:00",
        "created_at": f"{observed_on}T14:00:00-04:00",
        "updated_at": f"{observed_on}T15:00:00-04:00",
        "uri": f"https://www.inaturalist.org/observations/{observation_id}",
        "quality_grade": "needs_id",
        "obscured": False,
        "geoprivacy": None,
        "location": "42.2744,-76.4926",
        "private_location": "42.274401,-76.492601",
        "user": {"login": "observer", "name": "Observer"},
        "taxon": {
            "id": taxon_id,
            "name": scientific,
            "preferred_common_name": common,
            "rank": rank,
            "ancestor_ids": taxon_ancestors,
        },
        "community_taxon": None,
        "photos": photos or [
            {
                "id": 501,
                "url": "https://example.test/photos/501/square.jpg",
                "original_dimensions": {"width": 1600, "height": 1200},
                "attribution": "(c) Observer, CC BY-NC",
                "license_code": "cc-by-nc",
            },
            {
                "id": 502,
                "url": "https://example.test/photos/502/square.jpg",
                "original_dimensions": {"width": 1200, "height": 1600},
                "attribution": "(c) Observer, CC BY-NC",
                "license_code": "cc-by-nc",
            },
        ],
        "identifications": [
            {
                "id": 901,
                "current": True,
                "category": "leading",
                "body": "Date suggests the midsummer flight, but check the underside.",
                "created_at": f"{observed_on}T15:00:00-04:00",
                "user": {"login": "identifier", "name": "Identifier"},
                "taxon": {
                    "id": taxon_id,
                    "name": scientific,
                    "preferred_common_name": common,
                    "rank": rank,
                },
                "previous_observation_taxon": None,
            }
        ],
        "comments": [
            {
                "id": 801,
                "body": "The ventral forewing was not photographed.",
                "created_at": f"{observed_on}T16:00:00-04:00",
                "user": {"login": "commenter", "name": "Commenter"},
            }
        ],
    }


class TigerSwallowtailSourceTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(db.SCHEMA)

    def tearDown(self):
        self.conn.close()

    def test_target_species_complex_and_descendants_qualify(self):
        self.assertTrue(tiger.qualifies_observation(observation()))
        self.assertTrue(tiger.qualifies_observation(
            observation(taxon_id=tiger.EASTERN_TAXON_ID)
        ))
        self.assertTrue(tiger.qualifies_observation(
            observation(taxon_id=tiger.TIGER_COMPLEX_TAXON_ID)
        ))
        descendant = observation(
            taxon_id=999001,
            ancestor_ids=[47225, tiger.TIGER_COMPLEX_TAXON_ID, 999001],
        )
        self.assertTrue(tiger.qualifies_observation(descendant))
        unrelated = observation(taxon_id=47225, ancestor_ids=[47225])
        self.assertFalse(tiger.qualifies_observation(unrelated))

    def test_capture_preserves_first_source_taxon_during_reidentification(self):
        first = observation(taxon_id=tiger.MIDSUMMER_TAXON_ID)
        self.assertTrue(tiger.capture_observation(self.conn, first))

        changed = observation(taxon_id=tiger.EASTERN_TAXON_ID)
        self.assertTrue(tiger.capture_observation(self.conn, changed))
        row = self.conn.execute(
            "SELECT * FROM tiger_swallowtail_obs WHERE observation_id = 101"
        ).fetchone()
        payload = json.loads(row["payload_json"])

        self.assertEqual(tiger.MIDSUMMER_TAXON_ID, row["original_taxon_id"])
        self.assertEqual(tiger.EASTERN_TAXON_ID, row["current_taxon_id"])
        self.assertEqual(
            tiger.EASTERN_TAXON_ID, payload["source_taxon"]["id"]
        )

    def test_source_snapshot_keeps_all_public_evidence_but_no_coordinates(self):
        payload = tiger.normalize_observation(observation())
        self.assertEqual([501, 502], [photo["id"] for photo in payload["photos"]])
        self.assertEqual(1, len(payload["identifications"]))
        self.assertEqual(1, len(payload["comments"]))
        self.assertNotIn("latitude", json.dumps(payload))
        self.assertNotIn("longitude", json.dumps(payload))
        self.assertNotIn("42.2744", json.dumps(payload))
        self.assertFalse(payload["location"]["coordinates_published_here"])

    def test_existing_case_record_stays_refreshable_after_taxon_moves_out(self):
        self.assertTrue(tiger.capture_observation(self.conn, observation()))
        moved = observation(taxon_id=47225, ancestor_ids=[47225])
        moved["taxon"].update({
            "name": "Papilio",
            "preferred_common_name": "Common Swallowtails",
            "rank": "genus",
        })
        self.assertTrue(tiger.capture_observation(self.conn, moved))
        row = self.conn.execute(
            "SELECT current_taxon_id, original_taxon_id "
            "FROM tiger_swallowtail_obs"
        ).fetchone()
        self.assertEqual(47225, row["current_taxon_id"])
        self.assertEqual(tiger.MIDSUMMER_TAXON_ID, row["original_taxon_id"])

    def test_manual_review_can_include_broader_source_identification(self):
        broader = observation(taxon_id=47225, ancestor_ids=[47225])
        broader["taxon"].update({
            "name": "Papilio",
            "preferred_common_name": "Common Swallowtails",
            "rank": "genus",
        })

        self.assertFalse(tiger.capture_observation(self.conn, broader))
        self.assertTrue(tiger.capture_observation(
            self.conn, broader, manual_include=True
        ))
        row = self.conn.execute(
            "SELECT current_taxon_id, current_taxon_name "
            "FROM tiger_swallowtail_obs"
        ).fetchone()
        self.assertEqual(47225, row["current_taxon_id"])
        self.assertEqual("Papilio", row["current_taxon_name"])


class TigerSwallowtailAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.payload = tiger.normalize_observation(observation())

    def test_unreviewed_observation_is_insufficient_and_flagged(self):
        result = tiger.assess_observation(self.payload)
        self.assertEqual(
            "Insufficient photographic evidence", result["assessment"]
        )
        self.assertEqual("partial", result["view"])
        self.assertTrue(result["manual_review"])
        self.assertIn("no manual image annotation", result["review_reasons"][0])

    def test_dorsal_only_secondary_evidence_is_never_strong(self):
        result = tiger.assess_observation(self.payload, {
            "view": "dorsal",
            "wear": "fresh",
            "ventral_forewing_visible": False,
            "secondary_morphology_clear": True,
            "wing_shape": {"signal": "eastern", "note": "Concave margin."},
            "sex_or_dark_form": {
                "signal": "eastern",
                "note": "Female dorsal pattern leans Eastern.",
            },
            "image_limitations": ["No ventral view."],
        })
        self.assertEqual("Leaning Eastern", result["assessment"])

    def test_multiple_agreeing_morphology_traits_can_be_strong(self):
        result = tiger.assess_observation(self.payload, {
            "view": "ventral",
            "wear": "moderate",
            "ventral_forewing_visible": True,
            "ventral_forewing_pattern": "eastern",
            "ventral_forewing_note": "Discrete lunules.",
            "secondary_morphology_clear": True,
            "wing_shape": {"signal": "eastern", "note": "Concave margin."},
            "sex_or_dark_form": {"signal": "neutral", "note": "Not directional."},
            "image_limitations": ["Photographic assessment only."],
        })
        self.assertEqual("Strong Eastern", result["assessment"])
        self.assertTrue(result["manual_review"])  # July date conflicts.

    def test_conflicting_morphology_remains_unresolved(self):
        result = tiger.assess_observation(self.payload, {
            "view": "ventral",
            "wear": "fresh",
            "ventral_forewing_visible": True,
            "ventral_forewing_pattern": "midsummer",
            "ventral_forewing_note": "Band-like.",
            "secondary_morphology_clear": True,
            "wing_shape": {"signal": "eastern", "note": "Concave margin."},
            "sex_or_dark_form": {"signal": "neutral", "note": "Not directional."},
            "image_limitations": ["Traits conflict."],
        })
        self.assertEqual(
            "Unresolved Eastern/Midsummer", result["assessment"]
        )

    def test_all_six_assessment_labels_are_supported(self):
        expected = set(tiger.ASSESSMENTS)
        produced = {
            tiger._morphology_assessment({
                "ventral_forewing_visible": True,
                "ventral_forewing_pattern": "eastern",
                "secondary_morphology_clear": True,
                "wing_shape": {"signal": "eastern"},
            }),
            tiger._morphology_assessment({
                "ventral_forewing_visible": True,
                "ventral_forewing_pattern": "eastern",
            }),
            tiger._morphology_assessment({
                "ventral_forewing_visible": True,
                "ventral_forewing_pattern": "midsummer",
                "secondary_morphology_clear": True,
                "wing_shape": {"signal": "midsummer"},
            }),
            tiger._morphology_assessment({
                "ventral_forewing_visible": True,
                "ventral_forewing_pattern": "midsummer",
            }),
            tiger._morphology_assessment({
                "ventral_forewing_visible": True,
                "ventral_forewing_pattern": "mixed",
            }),
            tiger._morphology_assessment({}),
        }
        self.assertEqual(expected, produced)


class TigerSwallowtailBuildTests(unittest.TestCase):
    def test_photo_cache_attempts_every_distinct_photo(self):
        payload = tiger.normalize_observation(observation())
        with patch.object(
            tiger, "_download_photo", return_value=Path("/tmp/photo.jpg")
        ) as download:
            count, warnings = tiger.cache_photos(
                [payload, payload], cache_dir=Path("/tmp/test-cache")
            )
        self.assertEqual(2, count)
        self.assertEqual([], warnings)
        self.assertEqual(2, download.call_count)

    def test_page_keeps_source_and_assessment_separate_and_defaults_july_pair(self):
        july_23 = tiger.normalize_observation(observation(
            observation_id=384363724,
            taxon_id=tiger.MIDSUMMER_TAXON_ID,
            observed_on="2026-07-23",
        ))
        july_24 = tiger.normalize_observation(observation(
            observation_id=384696880,
            taxon_id=tiger.EASTERN_TAXON_ID,
            observed_on="2026-07-24",
        ))
        for payload in (july_23, july_24):
            payload["_source_record"] = {
                "original_taxon": dict(payload["source_taxon"]),
                "first_ingested_at": "2026-07-26 12:00:00",
                "last_synced_at": "2026-07-26 12:00:00",
            }

        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            reviews = {
                "schema_version": 1,
                "observations": {
                    "384363724": {
                        "assessment_override": "Insufficient photographic evidence",
                        "view": "dorsal",
                        "wear": "moderate",
                        "image_limitations": ["No underside."],
                    },
                    "384696880": {
                        "assessment_override": "Leaning Eastern",
                        "view": "dorsal",
                        "wear": "fresh",
                        "image_limitations": ["Secondary traits only."],
                    },
                },
            }
            review_path = temp / "reviews.json"
            review_path.write_text(json.dumps(reviews), encoding="utf-8")
            output = tiger.build(
                output_dir=temp / "site",
                review_path=review_path,
                cache_dir=temp / "cache",
                records=[july_23, july_24],
            )
            html = output.read_text(encoding="utf-8")

        self.assertIn("Current iNaturalist taxon", html)
        self.assertIn("Site analytical assessment", html)
        self.assertIn("Unresolved Eastern/Midsummer", html)
        self.assertIn("Ventral forewing not visible clearly enough", html)
        self.assertIn(
            '["384363724","384696880"]', html
        )
        self.assertIn(
            "transform-origin: var(--focus-x, 50%) var(--focus-y, 50%)",
            html,
        )
        self.assertIn(
            "TL;DR: a distinct midsummer species—but not a one-mark ID",
            html,
        )
        self.assertIn("The underside is the useful side.", html)
        self.assertIn(tiger.PAPER_FIGURE_6_IMAGE, html)
        self.assertIn(tiger.PAPER_FIGURE_7_IMAGE, html)
        self.assertIn("a · Midsummer", html)
        self.assertIn("b · Canadian", html)
        self.assertIn("c · Eastern", html)
        self.assertLess(html.index("b · Canadian"), html.index("a · Midsummer"))
        self.assertLess(html.index("a · Midsummer"), html.index("c · Eastern"))
        self.assertIn("Find the black strip at the hairy lower edge", html)
        self.assertIn("It is a body measurement, not an identification confidence", html)
        self.assertIn("a · Medium", html)
        self.assertIn("b · Thickest", html)
        self.assertIn("c · Thinnest", html)
        canadian_card = (
            '<p class="mt-1 font-serif text-xl font-semibold text-stone-950">'
            "Canadian</p>"
        )
        midsummer_card = (
            '<p class="mt-1 font-serif text-xl font-semibold text-stone-950">'
            "Midsummer</p>"
        )
        eastern_card = (
            '<p class="mt-1 font-serif text-xl font-semibold text-stone-950">'
            "Eastern</p>"
        )
        self.assertLess(html.index(canadian_card), html.index(midsummer_card))
        self.assertLess(html.index(midsummer_card), html.index(eastern_card))
        self.assertIn("About 30–55% of the cell", html)
        self.assertIn("A second clue: straight versus scalloped", html)
        self.assertIn("See all paper specimens in Figure 7", html)
        self.assertIn("some specimens cannot be separated", html)
        self.assertIn('value="384363724"', html)
        self.assertIn('value="384696880"', html)
        self.assertNotIn("42.2744", html)


if __name__ == "__main__":
    unittest.main()
