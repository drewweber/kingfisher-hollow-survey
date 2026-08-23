import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

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
                "#activity",
                "#phenology",
                "#observers",
                "#map",
            ],
        )

    def test_each_view_has_a_unique_static_route(self):
        routes = [config["route"] for config in report.VIEW_CONFIG.values()]
        self.assertEqual(len(routes), len(set(routes)))
        self.assertEqual("/", report.VIEW_CONFIG["all"]["route"])
        self.assertEqual("/life-list/", report.VIEW_CONFIG["life-list"]["route"])
        self.assertEqual("/log/", report.VIEW_CONFIG["log"]["route"])
        self.assertEqual("/dragonflies/", report.VIEW_CONFIG["odonates"]["route"])

    def test_moth_index_has_one_inventory_status_chapter(self):
        links = report.VIEW_CONFIG["moths"]["links"]
        self.assertIn(("#moth-completeness", "Inventory status"), links)
        self.assertNotIn("#moth-diversity", [href for href, _label in links])

    def test_navigation_has_accessible_menu_and_complete_index(self):
        html = report.nav("moths")
        self.assertIn('aria-label="Survey navigation"', html)
        self.assertIn('aria-controls="survey-menu"', html)
        self.assertIn('aria-expanded="false"', html)
        self.assertIn('id="skip-link"', html)
        self.assertIn('href="/moths/"', html)
        self.assertIn('aria-current="page"', html)
        self.assertNotIn('aria-pressed=', html)
        for href, _label in report.VIEW_CONFIG["moths"]["links"]:
            self.assertIn(f'href="{href}"', html)

    def test_log_links_to_social_export_and_tiger_swallowtail_guide(self):
        html = report.log_resource_links()
        self.assertIn('aria-labelledby="log-resources-title"', html)
        self.assertIn('href="/tools/social-export/"', html)
        self.assertIn("Social Media Export", html)
        self.assertIn('href="/tools/new-county-species/"', html)
        self.assertIn("New County Species Detector", html)
        self.assertIn(f'href="{report.tiger_swallowtail.CASE_ROUTE}"', html)
        self.assertIn("Tiger Swallowtail ID Guide", html)

    def test_stylesheet_url_changes_with_the_stylesheet_content(self):
        version = report._asset_version("src/styles.css")
        html = report.head({"species": 1}, county_firsts=0, mode="log")
        self.assertIn(f'href="/assets/survey.css?v={version}"', html)
        self.assertIn('href="https://survey.kingfisher-hollow.com/log/"', html)
        self.assertIn('data-mode="log"', html)
        self.assertNotIn("window.__plotlyQueue", html)

    def test_root_head_preserves_legacy_hash_redirects_before_body_parsing(self):
        html = report.head({"species": 1}, county_firsts=0, mode="all")
        self.assertIn("const routes=", html)
        self.assertIn('"log-journal":"/log/"', html)
        self.assertIn('"moth-diversity":"/moths/"', html)
        self.assertIn("location.replace(route+location.hash)", html)

    def test_route_output_paths_match_clean_pages_routes(self):
        self.assertEqual(report.PUBLIC_DIR / "index.html", report._view_output_path("all"))
        self.assertEqual(
            report.PUBLIC_DIR / "moths" / "index.html",
            report._view_output_path("moths"),
        )

    def test_dark_survey_menu_keeps_inactive_view_names_readable(self):
        styles = (Path(report.__file__).parent / "src/styles.css").read_text()
        rule_start = styles.index(".survey-view-grid .mode-btn {")
        rule_end = styles.index("}", rule_start)
        self.assertIn(
            "color: rgba(255, 255, 255, .78);",
            styles[rule_start:rule_end],
        )

    def test_gap_copy_discloses_exotic_target_filtering(self):
        gap = {
            "have": 1,
            "region_total": 2,
            "missing_count": 1,
            "missing": pd.DataFrame(),
        }

        self.assertIn("exotic pets are excluded", report.mammal_gap_body(gap))
        self.assertIn("exotic-pet taxa are excluded", report.amphibian_gap_body(gap))
        self.assertIn("exotic-pet taxa are excluded", report.reptile_gap_body(gap))

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

    def test_no_go_card_shows_reason_without_repeated_guidance(self):
        ranked = [
            {
                "date": "2099-07-01",
                "priority_rank": 1,
                "rating": "Focus",
                "action": "Full multi-station survey",
                "predicted_species": 59,
                "score": 73,
                "unsafe": False,
                "temp_f_9pm": 74,
                "humidity_9pm": 70,
                "wind_mph_9pm": 2,
                "rain_chance_pct": 10,
                "moon": "waxing gibbous",
                "moon_illumination_pct": 96,
                "typical_error": 22,
            },
            {
                "date": "2099-07-02",
                "rating": "Skip",
                "action": "Rest / process records",
                "predicted_species": 89,
                "score": 39,
                "unsafe": True,
                "skip_reason": "steady rain",
                "temp_f_9pm": 64,
                "humidity_9pm": 99,
                "wind_mph_9pm": 3,
                "rain_chance_pct": 92,
                "moon": "waxing gibbous",
                "moon_illumination_pct": 99,
                "typical_error": 22,
            },
        ]
        with mock.patch.object(
            report.analyze,
            "rank_moth_forecast",
            return_value=ranked,
        ):
            html = report.moth_forecast_body(
                {"nights": ranked},
                {"status": "insufficient", "nights": 0},
            )

        self.assertIn("Skip · steady rain", html)
        self.assertIn('tabular-nums">39</span>', html)
        self.assertNotIn('tabular-nums">89</span>', html)
        self.assertNotIn("Typical error", html)
        self.assertNotIn("Rest / process records", html)

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
        self.assertIn('href="#activity"', html)
        self.assertIn("Survey effort", html)
        self.assertIn("03 / 07", html)

    def test_legacy_chapter_links_can_be_preserved_as_aliases(self):
        html = report.anchor_alias("uniqueness", "gallery", "moth-diversity")
        for id_ in ("uniqueness", "gallery", "moth-diversity"):
            self.assertIn(f'id="{id_}"', html)
        self.assertEqual(html.count('class="anchor-alias"'), 3)

    def test_subsection_hashes_update_the_single_page_field_index(self):
        script = report.scripts("plants")
        self.assertIn("Each static page has one survey view", script)
        self.assertIn("const section=target?.matches('section[id]')", script)
        self.assertIn("window.addEventListener('hashchange',applyHash)", script)
        self.assertNotIn("function setMode(", script)

    def test_each_route_gets_only_its_feature_script(self):
        life = report.scripts("life-list")
        overview = report.scripts("all")
        moths = report.scripts("moths")
        log = report.scripts("log")
        plants = report.scripts("plants")

        self.assertIn("Life-list filters", life)
        self.assertNotIn("Life-list filters", overview)
        self.assertIn("data-plotly-chart", overview)
        self.assertIn(report.PLOTLY_CDN, overview)
        self.assertIn("data-plotly-chart", moths)
        self.assertNotIn("data-plotly-chart", life)
        self.assertIn("trigger a private survey data refresh", log)
        self.assertNotIn("trigger a private survey data refresh", plants)
        for script in (life, overview, moths, log, plants):
            self.assertNotIn("__LIFE_LIST_SCRIPT__", script)
            self.assertNotIn("__PLOTLY_SCRIPT__", script)
            self.assertNotIn("__LOG_UPDATE_SCRIPT__", script)

    def test_life_list_rows_reuse_visible_text_for_search_metadata(self):
        life = pd.DataFrame([
            {
                "first_seen": "2026-08-01",
                "first_observed_at": "2026-08-01T12:00:00-04:00",
                "last_seen": "2026-08-02",
                "taxon_id": 123,
                "label": "Example Bird",
                "taxon_name": "Avis example",
                "group": "Birds",
                "family_name": "Exampleidae",
                "observations": 2,
            },
            {
                "first_seen": "2026-07-01",
                "first_observed_at": "2026-07-01T12:00:00-04:00",
                "last_seen": "2026-07-01",
                "taxon_id": float("nan"),
                "label": "Synthetic Bird",
                "taxon_name": "Avis ficta",
                "group": "Birds",
                "family_name": "Exampleidae",
                "observations": 1,
            },
        ])

        html = report.life_list_body(life)

        self.assertEqual(2, html.count('class="ll-row"'))
        self.assertNotIn("data-order=", html)
        self.assertNotIn("data-name=", html)
        self.assertNotIn('<tr class="ll-row" data-group=', html)
        self.assertIn('data-family="Exampleidae"', html)
        self.assertIn('class="ll-species-cell"', html)
        self.assertIn('class="ll-group-cell">Birds</td>', html)
        self.assertIn("name:searchName(element)",
                      report.LIFE_LIST_SCRIPT)
        self.assertIn("return (common+' '+(scientificNode?.textContent||'')).toLowerCase()",
                      report.LIFE_LIST_SCRIPT)
        self.assertIn("group:(element.cells[2]?.textContent||'').trim()",
                      report.LIFE_LIST_SCRIPT)

    def test_reveals_remain_visible_without_intersection_observer(self):
        styles = (Path(report.__file__).parent / "src/styles.css").read_text()
        self.assertIn(".reveal { opacity: 1; transform: none; }", styles)
        self.assertIn(
            "html.scroll-reveal-ready .reveal { opacity: 0;",
            styles,
        )
        self.assertIn(
            "if(reveals.length&&'IntersectionObserver' in window&&!reduceMotion){\n"
            "    try{",
            report.scripts("plants"),
        )
        self.assertIn(
            "document.documentElement.classList.add('scroll-reveal-ready');",
            report.scripts("plants"),
        )
        self.assertIn(
            "if('IntersectionObserver' in window){\n"
            "      try{\n"
            "        const sectionObserver=new IntersectionObserver",
            report.scripts("plants"),
        )

    def test_life_list_uses_the_dark_page_text_palette(self):
        source = Path(report.__file__).read_text()
        start = source.index("    life_list_section = section(")
        end = source.index("    two_up = (", start)
        life_list_section = source[start:end]
        self.assertIn('text-hollow-300">Life List', life_list_section)
        self.assertIn("moth_portrait_showcase(df, dark=True)", life_list_section)
        self.assertIn("life_list_body(life, dark=True)", life_list_section)
        self.assertIn("dark=True", life_list_section)
        self.assertIn('heading = "text-white" if dark else "text-stone-900"', source)
        self.assertIn('copy = "text-white/60" if dark else "text-stone-500"', source)

        empty_life = mock.Mock()
        empty_life.empty = True
        empty = report.life_list_body(empty_life, dark=True)
        self.assertIn("text-white/50", empty)


if __name__ == "__main__":
    unittest.main()
