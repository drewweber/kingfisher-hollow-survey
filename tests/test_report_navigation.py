import unittest
from pathlib import Path

import report


class ReportNavigationTests(unittest.TestCase):
    def test_internal_section_ids_are_unique(self):
        ids = [
            href
            for config in report.VIEW_CONFIG.values()
            for href, _label in config["links"]
            if href.startswith("#")
        ]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_life_index_covers_the_full_report_arc(self):
        self.assertEqual(
            [href for href, _label in report.VIEW_CONFIG["all"]["links"]],
            [
                "#whats-new",
                "#discovery",
                "#unique",
                "#life-list",
                "#activity",
                "#phenology",
                "#observers",
                "#map",
            ],
        )

    def test_moth_index_has_one_inventory_status_chapter(self):
        links = report.VIEW_CONFIG["moths"]["links"]
        self.assertIn(("#moth-completeness", "Inventory status"), links)
        self.assertNotIn("#moth-diversity", [href for href, _label in links])

    def test_navigation_has_accessible_menu_and_complete_index(self):
        html = report.nav()
        self.assertIn('aria-label="Survey navigation"', html)
        self.assertIn('aria-controls="survey-menu"', html)
        self.assertIn('aria-expanded="false"', html)
        self.assertIn('id="skip-link"', html)
        for href, _label in report.VIEW_CONFIG["all"]["links"]:
            self.assertIn(f'href="{href}"', html)

    def test_stylesheet_url_changes_with_the_stylesheet_content(self):
        version = report._asset_version("src/styles.css")
        html = report.head({"species": 1}, county_firsts=0)
        self.assertIn(f'href="/assets/survey.css?v={version}"', html)

    def test_dark_survey_menu_keeps_inactive_view_names_readable(self):
        styles = (Path(report.__file__).parent / "src/styles.css").read_text()
        rule_start = styles.index(".survey-view-grid .mode-btn {")
        rule_end = styles.index("}", rule_start)
        self.assertIn(
            "color: rgba(255, 255, 255, .78);",
            styles[rule_start:rule_end],
        )

    def test_moth_forecast_distinguishes_detection_from_presence(self):
        forecast = {
            "nights": [
                {
                    "date": "2099-07-01",
                    "temp_f_9pm": 70,
                    "humidity_9pm": 70,
                    "wind_mph_9pm": 2,
                    "wind_dir_9pm": "S",
                    "rain_chance_pct": 5,
                    "precip_in": 0,
                    "moon": "waning crescent",
                    "moon_illumination_pct": 10,
                }
            ]
        }
        html = report.moth_forecast_body(
            forecast,
            {"status": "insufficient", "nights": 0},
        )
        self.assertIn("estimates documented richness", html)
        self.assertIn("not that moths are absent", html)
        self.assertIn("Temperature and moonlight are clues, not switches", html)
        self.assertIn("not the property’s true presence or absence", html)

    def test_section_flow_follows_the_configured_reading_order(self):
        html = report.section(
            "unique",
            "Distinctiveness",
            "What Stands Out",
            "<p>Body</p>",
        )
        self.assertIn('aria-labelledby="unique-title"', html)
        self.assertIn('id="unique-title"', html)
        self.assertIn('href="#discovery"', html)
        self.assertIn("Growth", html)
        self.assertIn('href="#life-list"', html)
        self.assertIn("Life list", html)
        self.assertIn("03 / 08", html)

    def test_legacy_chapter_links_can_be_preserved_as_aliases(self):
        html = report.anchor_alias("uniqueness", "gallery", "moth-diversity")
        for id_ in ("uniqueness", "gallery", "moth-diversity"):
            self.assertIn(f'id="{id_}"', html)
        self.assertEqual(html.count('class="anchor-alias"'), 3)

    def test_subsection_hashes_resolve_their_own_view(self):
        self.assertIn("function modeForHash(hash)", report.SCRIPTS)
        self.assertIn("closest('[id^=\"view-\"]')", report.SCRIPTS)
        self.assertIn("const hashSection=hashTarget?.matches('section[id]')", report.SCRIPTS)
        self.assertIn("window.addEventListener('hashchange',applyHash)", report.SCRIPTS)


if __name__ == "__main__":
    unittest.main()
