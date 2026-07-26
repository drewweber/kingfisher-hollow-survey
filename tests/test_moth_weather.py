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
    def test_fixed_window_uses_local_photo_time_and_distinct_species(self):
        observations = pd.DataFrame([
            {
                "id": 1, "taxon_id": 10,
                "observed_on": pd.Timestamp("2026-08-01"),
                "observed_at": "2026-08-01T20:59:00-04:00",
            },
            {
                "id": 2, "taxon_id": 10,
                "observed_on": pd.Timestamp("2026-08-01"),
                "observed_at": "2026-08-01T21:15:00-04:00",
            },
            {
                "id": 3, "taxon_id": 11,
                "observed_on": pd.Timestamp("2026-08-01"),
                "observed_at": "2026-08-01T22:59:00-04:00",
            },
            {
                "id": 4, "taxon_id": 12,
                "observed_on": pd.Timestamp("2026-08-01"),
                "observed_at": "2026-08-01T23:00:00-04:00",
            },
        ])

        result = analyze._moth_fixed_window_counts(observations)

        self.assertEqual(result.iloc[0]["species_count"], 2)
        self.assertEqual(result.iloc[0]["night"], pd.Timestamp("2026-08-01"))

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
        self.assertEqual(ranked[0]["action"], "2-hour focused sheet")
        self.assertEqual(ranked[1]["rating"], "Skip")

    def test_one_lower_scoring_safe_night_becomes_fixed_calibration(self):
        def night(date, temp, rain):
            return {
                "date": date,
                "temp_f_9pm": temp,
                "humidity_9pm": 65,
                "wind_mph_9pm": 4,
                "rain_chance_pct": rain,
                "precip_in": 0,
                "moon_illumination_pct": 40,
            }

        ranked = analyze.rank_moth_forecast([
            night("2026-08-01", 75, 0),
            night("2026-08-02", 72, 5),
            night("2026-08-03", 55, 40),
            night("2026-08-04", 51, 45),
        ])

        calibration = [row for row in ranked if row.get("is_calibration")]
        self.assertEqual(len(calibration), 1)
        self.assertEqual(calibration[0]["action"], "60-minute calibration")


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
