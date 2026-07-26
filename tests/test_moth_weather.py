import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import analyze  # noqa: E402
import weather  # noqa: E402


class MothWeatherAnalysisTests(unittest.TestCase):
    def test_full_night_counts_species_and_ignores_travel_gaps(self):
        observations = pd.DataFrame([
            {
                "id": 1, "taxon_id": 10,
                "observed_on": pd.Timestamp("2026-08-01"),
                "observed_at": "2026-08-01T20:00:00-04:00",
            },
            {
                "id": 2, "taxon_id": 11,
                "observed_on": pd.Timestamp("2026-08-01"),
                "observed_at": "2026-08-01T21:15:00-04:00",
            },
            {
                "id": 3, "taxon_id": 12,
                "observed_on": pd.Timestamp("2026-08-02"),
                "observed_at": "2026-08-02T05:00:00-04:00",
            },
            {
                "id": 4, "taxon_id": 99,
                "observed_on": pd.Timestamp("2026-08-01"),
                "observed_at": "2026-08-01T14:00:00-04:00",
            },
            {
                "id": 5, "taxon_id": 13,
                "observed_on": pd.Timestamp("2026-08-02"),
                "observed_at": "2026-08-02T20:00:00-04:00",
            },
        ])

        result = analyze._moth_full_night_counts(
            observations, min_observations=3
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["species_count"], 3)
        self.assertEqual(result.iloc[0]["night"], pd.Timestamp("2026-08-01"))
        self.assertGreater(result.iloc[0]["session_span_minutes"], 60)

    def test_full_effort_requires_more_than_thirty_observations(self):
        observations = []
        for index in range(30):
            observations.append({
                "id": index,
                "taxon_id": index,
                "observed_on": pd.Timestamp("2026-08-01"),
                "observed_at": (
                    "2026-08-01T20:00:00-04:00"
                    if index == 0
                    else "2026-08-01T21:01:00-04:00"
                ),
            })

        self.assertTrue(
            analyze._moth_full_night_counts(
                pd.DataFrame(observations)
            ).empty
        )

        observations.append({
            "id": 30,
            "taxon_id": 30,
            "observed_on": pd.Timestamp("2026-08-01"),
            "observed_at": "2026-08-01T20:30:00-04:00",
        })
        result = analyze._moth_full_night_counts(
            pd.DataFrame(observations)
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["observation_count"], 31)

    def test_focus_score_prefers_warm_calm_dry_dark_night(self):
        nights = [
            {
                "date": "2026-08-01",
                "temp_f_9pm": 72,
                "humidity_9pm": 78,
                "wind_mph_9pm": 2,
                "rain_chance_pct": 5,
                "precip_in": 0,
                "moon_illumination_pct": 8,
            },
            {
                "date": "2026-08-02",
                "temp_f_9pm": 52,
                "humidity_9pm": 48,
                "wind_mph_9pm": 11,
                "rain_chance_pct": 70,
                "precip_in": 0.2,
                "moon_illumination_pct": 96,
            },
        ]

        ranked = analyze.rank_moth_forecast(nights)

        self.assertGreater(ranked[0]["score"], ranked[1]["score"])
        self.assertEqual(ranked[0]["rating"], "Focus")
        self.assertEqual(ranked[0]["action"], "Full multi-station survey")
        self.assertEqual(ranked[1]["rating"], "Skip")

    def test_supported_model_ranks_by_predicted_whole_night_species(self):
        def night(date, temp):
            return {
                "date": date,
                "temp_f_9pm": temp,
                "humidity_9pm": 65,
                "wind_mph_9pm": 4,
                "rain_chance_pct": 10,
                "precip_in": 0,
                "moon_illumination_pct": 40,
                "moon_phase": 0.2,
            }

        coefficients = [50.0] + [0.0] * 9
        coefficients[5] = 5.0
        analysis = {
            "status": "supported",
            "weather_mae": 10,
            "prediction_model": {
                "feature_mean": [0, 0, 0, 0, 65, 65, 4, 0, 0.4],
                "feature_scale": [1] * 9,
                "coefficients": coefficients,
                "historical_median": 40,
            },
        }
        ranked = analyze.rank_moth_forecast([
            night("2026-08-01", 60),
            night("2026-08-02", 70),
            night("2026-08-03", 65),
        ], analysis=analysis)

        by_date = {row["date"]: row for row in ranked}
        self.assertEqual(by_date["2026-08-02"]["rating"], "Focus")
        self.assertEqual(
            by_date["2026-08-02"]["action"],
            "Full multi-station survey",
        )
        self.assertGreater(
            by_date["2026-08-02"]["predicted_species"],
            by_date["2026-08-01"]["predicted_species"],
        )
        self.assertEqual(by_date["2026-08-02"]["typical_error"], 10)

    def test_no_go_weather_names_the_skip_reason(self):
        analysis = {
            "status": "supported",
            "weather_mae": 22,
            "prediction_model": {
                "feature_mean": [0] * 9,
                "feature_scale": [1] * 9,
                "coefficients": [89.0] + [0.0] * 9,
                "historical_median": 40,
            },
        }
        ranked = analyze.rank_moth_forecast([{
            "date": "2026-07-28",
            "temp_f_9pm": 64,
            "humidity_9pm": 99,
            "wind_mph_9pm": 3,
            "rain_chance_pct": 92,
            "precip_in": 1.19,
            "moon_illumination_pct": 99,
            "moon_phase": 0.49,
        }], analysis=analysis)

        self.assertEqual(ranked[0]["predicted_species"], 89)
        self.assertEqual(ranked[0]["rating"], "Skip")
        self.assertEqual(ranked[0]["skip_reason"], "rain")
        self.assertLessEqual(ranked[0]["score"], 39)


class ForecastTests(unittest.TestCase):
    def test_forecast_parser_extracts_nine_pm_and_moon(self):
        response = {
            "daily": {
                "time": ["2026-08-01"],
                "precipitation_sum": [2.54],
                "precipitation_probability_max": [30],
            },
            "hourly": {
                "time": ["2026-08-01T21:00"],
                "temperature_2m": [20],
                "relative_humidity_2m": [74],
                "wind_speed_10m": [8.04672],
                "wind_direction_10m": [225],
                "cloud_cover": [60],
                "precipitation_probability": [20],
            },
        }

        row = weather._forecast_rows(response)[0]

        self.assertEqual(row["date"], "2026-08-01")
        self.assertEqual(row["temp_f_9pm"], 68)
        self.assertEqual(row["wind_mph_9pm"], 5)
        self.assertEqual(row["precip_in"], 0.1)
        self.assertEqual(row["rain_chance_pct"], 30)
        self.assertIn("moon", row)
        self.assertGreaterEqual(row["moon_illumination_pct"], 0)
        self.assertLessEqual(row["moon_illumination_pct"], 100)

    def test_cached_forecast_survives_fetch_failure(self):
        today = datetime.date.today()
        cached_night = {
            "date": today.isoformat(),
            "temp_f_9pm": 65,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = Path(temp_dir) / "forecast.json"
            cache.write_text(json.dumps({
                "fetched_at": "2026-07-26T12:00:00+00:00",
                "nights": [cached_night],
            }), encoding="utf-8")
            with (
                mock.patch.object(weather, "_FORECAST_CACHE", cache),
                mock.patch.object(
                    weather,
                    "_FORECAST_CACHE_TTL_SECONDS",
                    0,
                ),
                mock.patch.object(
                    weather,
                    "_fetch_forecast",
                    side_effect=OSError("offline"),
                ),
            ):
                result = weather.load_forecast()

        self.assertEqual(result["source"], "cache")
        self.assertEqual(result["nights"], [cached_night])


if __name__ == "__main__":
    unittest.main()
