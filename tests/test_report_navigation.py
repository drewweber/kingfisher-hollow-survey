import unittest
from datetime import datetime, timezone
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

    def test_taxa_page_flags_cover_the_dedicated_group_pages(self):
        self.assertEqual(
            [
                "moths",
                "butterflies",
                "odonates",
                "birds",
                "mammals",
                "plants",
                "amphibians",
            ],
            [
                mode
                for mode, config in report.VIEW_CONFIG.items()
                if config.get("taxa_group")
            ],
        )

    def test_log_taxa_pills_link_every_group_page_with_its_total(self):
        modes = [
            mode
            for mode, config in report.VIEW_CONFIG.items()
            if config.get("taxa_group")
        ]
        totals = {
            mode: total
            for mode, total in zip(modes, [1234, 0, 33, 141, 22, 261, 17])
        }
        recent = {
            mode: total
            for mode, total in zip(modes, [42, 0, 3, None, 0, 6, 1])
        }

        html = report.log_taxa_total_pills(totals, recent)

        self.assertIn('aria-label="Species totals by survey group"', html)
        self.assertIn("+ first documented in 30 days", html)
        self.assertNotIn("— unavailable", html)
        self.assertIn("tabular-nums", html)
        self.assertEqual(len(modes), html.count("<li>"))
        self.assertEqual(len(modes), html.count("min-h-11 min-w-20"))
        self.assertEqual(len(modes), html.count("focus-visible:ring-2"))
        self.assertNotIn("rounded-full", html)
        for mode in modes:
            config = report.VIEW_CONFIG[mode]
            self.assertIn(f'href="{config["route"]}"', html)
            self.assertIn(f'>{config["label"]}</span>', html)
            self.assertIn(f'>{totals[mode]:,}</span>', html)
        self.assertIn(">+42</span>", html)
        self.assertIn("42 first documented in the last 30 days", html)
        self.assertIn("none first documented in the last 30 days", html)
        self.assertIn("30-day first-documented count unavailable", html)
        self.assertIn(
            'class="text-xs font-semibold text-stone-600" aria-hidden="true">—</span>',
            html,
        )
        self.assertNotIn(">+0</span>", html)
        self.assertNotIn('href="/log/"', html)
        self.assertNotIn("Overview", html)
        self.assertNotIn("Life list", html)

    def test_log_taxa_pills_require_a_total_for_every_group_page(self):
        with self.assertRaisesRegex(ValueError, "Missing Log taxon totals"):
            report.log_taxa_total_pills({})

    def test_log_taxa_pills_require_recent_data_for_every_group_when_supplied(self):
        totals = {
            mode: 1
            for mode, config in report.VIEW_CONFIG.items()
            if config.get("taxa_group")
        }
        with self.assertRaisesRegex(ValueError, "Missing Log recent taxon counts"):
            report.log_taxa_total_pills(totals, {})

    def test_log_taxa_pills_explain_when_all_recent_counts_are_unavailable(self):
        totals = {
            mode: 1
            for mode, config in report.VIEW_CONFIG.items()
            if config.get("taxa_group")
        }
        recent = {mode: None for mode in totals}

        html = report.log_taxa_total_pills(totals, recent)

        self.assertIn("30-day data unavailable", html)
        self.assertNotIn("+ first documented in 30 days", html)
        self.assertEqual(len(totals), html.count('aria-hidden="true">—</span>'))

    def test_log_taxa_pills_do_not_claim_recent_data_when_none_was_supplied(self):
        totals = {
            mode: 1
            for mode, config in report.VIEW_CONFIG.items()
            if config.get("taxa_group")
        }

        html = report.log_taxa_total_pills(totals)

        self.assertIn("Species totals", html)
        self.assertNotIn("first documented", html)
        self.assertNotIn("unavailable", html)
        self.assertNotIn(">—</span>", html)

    def test_log_update_control_leads_with_the_last_data_sync_time(self):
        html = report.log_update_control(
            datetime(2026, 8, 23, 20, 17, tzinfo=timezone.utc)
        )

        self.assertIn('<button id="trigger-update" type="button"', html)
        self.assertIn('aria-label="Check for updates"', html)
        self.assertIn('aria-describedby="trigger-update-status"', html)
        self.assertIn("Last updated", html)
        self.assertLess(html.index("Last updated"), html.index('<button id="trigger-update"'))
        self.assertIn(
            '<time datetime="2026-08-23T20:17:00Z"',
            html,
        )
        self.assertIn("Aug 23 · 4:17 PM ET</time>", html)
        self.assertIn('aria-hidden="true">↻</span>', html)
        self.assertIn("Check now</button>", html)
        self.assertIn("min-h-11", html)
        self.assertIn('id="trigger-update-status"', html)
        self.assertNotIn(">Check for updates...</button>", html)

    def test_log_update_control_discloses_a_missing_sync_time(self):
        html = report.log_update_control(None)

        self.assertIn("Last updated", html)
        self.assertIn(">Time unavailable</span>", html)
        self.assertNotIn("<time", html)
        self.assertIn("Check now</button>", html)

    def test_empty_log_keeps_the_refresh_action_available(self):
        html = report.activity_log_body([], {}, None)

        self.assertIn("No entries yet.", html)
        self.assertIn("Time unavailable", html)
        self.assertIn("Check now</button>", html)
        self.assertEqual(1, html.count('id="trigger-update"'))

    def test_data_updated_date_treats_sqlite_timestamp_as_utc(self):
        connection = mock.MagicMock()
        connection.execute.return_value.fetchone.return_value = {
            "t": "2026-08-23 20:15:00",
        }
        context = mock.MagicMock()
        context.__enter__.return_value = connection

        with mock.patch.object(report, "connect", return_value=context):
            self.assertEqual(
                datetime(2026, 8, 23, 20, 15, tzinfo=timezone.utc),
                report.data_updated_at(),
            )
            self.assertEqual("Aug 23 · 4:15pm", report.data_updated_date())

    def test_data_updated_at_normalizes_an_offset_aware_timestamp(self):
        connection = mock.MagicMock()
        connection.execute.return_value.fetchone.return_value = {
            "t": "2026-08-23T16:15:00-04:00",
        }
        context = mock.MagicMock()
        context.__enter__.return_value = connection

        with mock.patch.object(report, "connect", return_value=context):
            self.assertEqual(
                datetime(2026, 8, 23, 20, 15, tzinfo=timezone.utc),
                report.data_updated_at(),
            )

    def test_data_updated_at_can_scope_the_window_to_property_syncs(self):
        connection = mock.MagicMock()
        connection.execute.return_value.fetchone.return_value = {
            "t": "2026-08-23 20:15:00",
        }
        context = mock.MagicMock()
        context.__enter__.return_value = connection

        with mock.patch.object(report, "connect", return_value=context):
            updated = report.data_updated_at("property")

        self.assertEqual(
            datetime(2026, 8, 23, 20, 15, tzinfo=timezone.utc),
            updated,
        )
        connection.execute.assert_called_once_with(
            "SELECT MAX(synced_at) AS t FROM sync_log WHERE source = ?",
            ("property",),
        )

    def test_data_updated_date_does_not_claim_a_sync_when_none_exists(self):
        connection = mock.MagicMock()
        connection.execute.return_value.fetchone.return_value = {"t": None}
        context = mock.MagicMock()
        context.__enter__.return_value = connection

        with mock.patch.object(report, "connect", return_value=context):
            self.assertEqual("—", report.data_updated_date())

    def test_data_updated_at_rejects_malformed_or_non_text_values(self):
        for raw in ("not-a-time", 12345):
            with self.subTest(raw=raw):
                connection = mock.MagicMock()
                connection.execute.return_value.fetchone.return_value = {"t": raw}
                context = mock.MagicMock()
                context.__enter__.return_value = connection

                with mock.patch.object(report, "connect", return_value=context):
                    self.assertIsNone(report.data_updated_at())

    def test_data_updated_at_handles_a_sqlite_error(self):
        connection = mock.MagicMock()
        connection.execute.side_effect = report.SQLiteError("missing table")
        context = mock.MagicMock()
        context.__enter__.return_value = connection

        with mock.patch.object(report, "connect", return_value=context):
            self.assertIsNone(report.data_updated_at())

    def test_taxa_page_totals_match_each_page_summary_contract(self):
        def roster(*ids):
            return pd.DataFrame({"taxon_id": ids})

        birds = pd.DataFrame({
            "date": pd.to_datetime(["2026-08-01", "2026-08-02"]),
            "sub_id": ["S1", "S2"],
            "exotic": ["", ""],
        })
        empty_observations = pd.DataFrame(columns=["taxon_id", "observed_on"])
        loaders = {
            "load_butterflies": roster(10, 11),
            "load_odonates": roster(20, 21, 22),
            "load_mammals": roster(30, 31, 32, 33),
            "load_plants": roster(40, 41, 42, 43, 44),
            "load_amphibians": roster(50, 51),
            "load_reptiles": roster(60, 61, 62),
        }
        patches = {
            name: mock.Mock(return_value=value)
            for name, value in loaders.items()
        }
        with mock.patch.multiple(report.analyze, **patches):
            totals = report.taxa_page_species_totals(
                empty_observations,
                birds=birds,
                moths=roster(1, 2, 2),
            )

        self.assertEqual({
            "moths": 2,
            "butterflies": 2,
            "odonates": 3,
            "birds": 2,
            "mammals": 4,
            "plants": 5,
            "amphibians": 5,
        }, totals)

    def test_recent_taxa_counts_use_first_seen_dates_in_a_30_day_window(self):
        def roster(*ids):
            return pd.DataFrame({"taxon_id": ids})

        observations = pd.DataFrame({
            "taxon_id": [1, 1, 2, 10, 11, 20, 30, 40, 50, 60, 999],
            "observed_on": pd.to_datetime([
                "2026-07-25",  # window boundary, counted once despite duplicate
                "2026-08-20",
                "2026-07-24",  # one day before the window
                "2026-08-23",
                "2026-08-24",  # future observation is excluded
                "2026-07-01",
                "2026-07-25",
                "2026-08-10",
                "2026-07-24",
                "2026-08-01",
                "2026-08-12",  # recent, but not on a page roster
            ]),
        })
        loaders = {
            "load_butterflies": roster(10, 11),
            "load_odonates": roster(20),
            "load_mammals": roster(30),
            "load_plants": roster(40),
            "load_amphibians": roster(50),
            "load_reptiles": roster(60),
        }
        patches = {
            name: mock.Mock(return_value=value)
            for name, value in loaders.items()
        }
        with mock.patch.multiple(report.analyze, **patches):
            recent = report.taxa_page_recent_species(
                observations,
                birds=pd.DataFrame(),
                moths=roster(1, 2),
                as_of=datetime(2026, 8, 23, 16, tzinfo=timezone.utc),
            )

        self.assertEqual({
            "moths": 1,
            "butterflies": 1,
            "odonates": 0,
            "birds": None,
            "mammals": 1,
            "plants": 1,
            "amphibians": 1,
        }, recent)

    def test_recent_taxa_counts_are_unavailable_when_roster_coverage_is_missing(self):
        empty = pd.DataFrame({"taxon_id": pd.Series(dtype="int64")})
        loaders = {
            "load_butterflies": empty,
            "load_odonates": empty,
            "load_mammals": pd.DataFrame({"taxon_id": [30]}),
            "load_plants": empty,
            "load_amphibians": empty,
            "load_reptiles": empty,
        }
        patches = {
            name: mock.Mock(return_value=value)
            for name, value in loaders.items()
        }
        observations = pd.DataFrame({
            "taxon_id": pd.Series(dtype="int64"),
            "observed_on": pd.to_datetime([]),
        })
        with mock.patch.multiple(report.analyze, **patches):
            recent = report.taxa_page_recent_species(
                observations,
                birds=pd.DataFrame(),
                moths=empty,
                as_of=datetime(2026, 8, 23, tzinfo=timezone.utc),
            )

        self.assertIsNone(recent["mammals"])
        self.assertEqual(0, recent["moths"])
        self.assertIsNone(recent["birds"])

    def test_recent_taxa_counts_include_older_infraspecific_documentation(self):
        empty = pd.DataFrame({
            "taxon_id": pd.Series(dtype="int64"),
            "taxon_name": pd.Series(dtype="object"),
        })
        loaders = {
            "load_butterflies": pd.DataFrame({
                "taxon_id": [60607],
                "taxon_name": ["Limenitis arthemis"],
            }),
            "load_odonates": empty,
            "load_mammals": empty,
            "load_plants": pd.DataFrame({
                "taxon_id": [46142],
                "taxon_name": ["Quercus alba"],
            }),
            "load_amphibians": empty,
            "load_reptiles": empty,
        }
        patches = {
            name: mock.Mock(return_value=value)
            for name, value in loaders.items()
        }
        observations = pd.DataFrame({
            "taxon_id": [58585, 60607, 999999, 46142],
            "taxon_name": [
                "Limenitis arthemis astyanax",
                "Limenitis arthemis",
                "Quercus alba × Quercus rubra",
                "Quercus alba",
            ],
            "rank": ["subspecies", "species", "hybrid", "species"],
            "observed_on": pd.to_datetime([
                "2026-06-13", "2026-08-09", "2026-06-01", "2026-08-10",
            ]),
        })
        with mock.patch.multiple(report.analyze, **patches):
            recent = report.taxa_page_recent_species(
                observations,
                birds=pd.DataFrame(),
                moths=empty,
                as_of=datetime(2026, 8, 23, 16, tzinfo=timezone.utc),
            )

        self.assertEqual(0, recent["butterflies"])
        self.assertEqual(1, recent["plants"])

    def test_recent_taxa_counts_are_unavailable_without_a_property_sync_time(self):
        empty = pd.DataFrame({"taxon_id": pd.Series(dtype="int64")})
        loaders = {
            "load_butterflies": empty,
            "load_odonates": empty,
            "load_mammals": empty,
            "load_plants": empty,
            "load_amphibians": empty,
            "load_reptiles": empty,
        }
        patches = {
            name: mock.Mock(return_value=value)
            for name, value in loaders.items()
        }
        with mock.patch.multiple(report.analyze, **patches):
            recent = report.taxa_page_recent_species(
                pd.DataFrame(columns=["taxon_id", "observed_on"]),
                birds=pd.DataFrame(),
                moths=empty,
                as_of=None,
            )

        self.assertTrue(all(value is None for value in recent.values()))

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

    def test_stylesheet_url_uses_the_generated_stylesheet_hash(self):
        with mock.patch.object(report, "_asset_version", return_value="generated123") as version:
            html = report.head({"species": 1}, county_firsts=0, mode="log")

        version.assert_called_once_with("public/assets/survey.css")
        self.assertIn('href="/assets/survey.css?v=generated123"', html)
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
