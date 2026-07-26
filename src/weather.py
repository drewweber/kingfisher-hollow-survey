"""Weather data for the activity log and moth-night planning.

Historical conditions are cached in SQLite.  The shorter-lived Open-Meteo
forecast is cached as JSON so a temporary API failure does not remove the
planning panel from the published report.
"""

import datetime
import json
import math
import time
import urllib.parse
import urllib.request

from config import DATA_DIR, PROPERTY_LAT, PROPERTY_LON
from db import connect

_OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
_OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
_FORECAST_CACHE = DATA_DIR / "cache" / "moth_forecast.json"
_FORECAST_CACHE_TTL_SECONDS = 3 * 60 * 60

# Cardinal direction labels for wind bearing (16 points).
_WIND_DIRS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def _kmh_to_mph(v):
    return v * 0.621371


def _c_to_f(v):
    return v * 9 / 5 + 32


def _cardinal(deg):
    if deg is None:
        return ""
    idx = round(deg / 22.5) % 16
    return _WIND_DIRS[idx]


def wind_description(speed_mph, dir_deg):
    """Return a brief human-readable wind description, e.g. 'light SW wind'."""
    if speed_mph is None:
        return ""
    if speed_mph < 3:
        return "calm"
    if speed_mph < 8:
        adj = "light"
    elif speed_mph < 18:
        adj = "moderate"
    elif speed_mph < 30:
        adj = "strong"
    else:
        adj = "gusty"
    card = _cardinal(dir_deg)
    return f"{adj} {card} wind" if card else f"{adj} wind"


# Reference new moon: Jan 6, 2000 at noon UTC.
_REF_NEW_MOON = datetime.date(2000, 1, 6)
_SYNODIC_MONTH = 29.53059  # days


def moon_phase(date):
    """Return (fraction, emoji_name) for the given date.

    fraction: 0 = new moon, 0.5 = full moon.
    """
    age = (date - _REF_NEW_MOON).days % _SYNODIC_MONTH
    fraction = age / _SYNODIC_MONTH
    if age < 1.85 or age > 27.68:
        return fraction, "🌑 new moon"
    elif age < 7.38:
        return fraction, "🌒 waxing crescent"
    elif age < 9.22:
        return fraction, "🌓 first quarter"
    elif age < 14.77:
        return fraction, "🌔 waxing gibbous"
    elif age < 16.61:
        return fraction, "🌕 full moon"
    elif age < 22.15:
        return fraction, "🌖 waning gibbous"
    elif age < 23.99:
        return fraction, "🌗 last quarter"
    else:
        return fraction, "🌘 waning crescent"


def _fetch_range(start_date, end_date):
    """Fetch daily + hourly weather from Open-Meteo for a date range.

    Returns {date_str: {temp_f_hi, temp_f_lo, humidity_pct, wind_mph,
                        wind_dir_deg, precip_in,
                        temp_f_9pm, humidity_9pm, wind_mph_9pm, wind_dir_9pm}}
    Open-Meteo archive has a ~5-day lag; dates too recent are silently absent.
    """
    params = urllib.parse.urlencode({
        "latitude": PROPERTY_LAT,
        "longitude": PROPERTY_LON,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "daily": ",".join([
            "temperature_2m_max",
            "temperature_2m_min",
            "relative_humidity_2m_mean",
            "windspeed_10m_max",
            "winddirection_10m_dominant",
            "precipitation_sum",
        ]),
        "hourly": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "windspeed_10m",
            "winddirection_10m",
        ]),
        "timezone": "America/New_York",
        "temperature_unit": "celsius",
        "windspeed_unit": "kmh",
        "precipitation_unit": "mm",
    })
    url = f"{_OPEN_METEO_ARCHIVE}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        print(f"  weather fetch failed: {exc}")
        return {}

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    t_max = daily.get("temperature_2m_max", [])
    t_min = daily.get("temperature_2m_min", [])
    hum = daily.get("relative_humidity_2m_mean", [])
    wspd = daily.get("windspeed_10m_max", [])
    wdir = daily.get("winddirection_10m_dominant", [])
    precip = daily.get("precipitation_sum", [])

    # Build a lookup from "YYYY-MM-DDTHH:00" → hourly value index.
    hourly = data.get("hourly", {})
    h_times = hourly.get("time", [])
    h_temp  = hourly.get("temperature_2m", [])
    h_hum   = hourly.get("relative_humidity_2m", [])
    h_wspd  = hourly.get("windspeed_10m", [])
    h_wdir  = hourly.get("winddirection_10m", [])
    h_idx   = {t: i for i, t in enumerate(h_times)}

    def _9pm(date_str, lst):
        key = f"{date_str}T21:00"
        i = h_idx.get(key)
        if i is None or i >= len(lst):
            return None
        v = lst[i]
        return None if v is None or v != v else v

    out = {}
    for i, d in enumerate(dates):
        def _get(lst):
            v = lst[i] if i < len(lst) else None
            return None if v is None or v != v else v  # NaN → None

        hi_c = _get(t_max)
        lo_c = _get(t_min)

        t9_c  = _9pm(d, h_temp)
        h9    = _9pm(d, h_hum)
        ws9   = _9pm(d, h_wspd)
        wd9   = _9pm(d, h_wdir)

        out[d] = {
            "temp_f_hi": round(_c_to_f(hi_c)) if hi_c is not None else None,
            "temp_f_lo": round(_c_to_f(lo_c)) if lo_c is not None else None,
            "humidity_pct": round(_get(hum)) if _get(hum) is not None else None,
            "wind_mph": round(_kmh_to_mph(_get(wspd)), 1) if _get(wspd) is not None else None,
            "wind_dir_deg": round(_get(wdir)) if _get(wdir) is not None else None,
            "precip_in": round(_get(precip) * 0.0393701, 2) if _get(precip) is not None else None,
            "temp_f_9pm":   round(_c_to_f(t9_c)) if t9_c is not None else None,
            "humidity_9pm": round(h9) if h9 is not None else None,
            "wind_mph_9pm": round(_kmh_to_mph(ws9), 1) if ws9 is not None else None,
            "wind_dir_9pm": round(wd9) if wd9 is not None else None,
        }
    return out


def moon_illumination(fraction):
    """Approximate illuminated fraction of the moon, from 0 (new) to 1 (full)."""
    if fraction is None:
        return None
    return (1 - math.cos(2 * math.pi * fraction)) / 2


def _forecast_rows(data):
    """Normalize one Open-Meteo forecast response into nightly planning rows."""
    daily = data.get("daily", {})
    hourly = data.get("hourly", {})
    daily_dates = daily.get("time", [])
    daily_precip = daily.get("precipitation_sum", [])
    daily_rain_chance = daily.get("precipitation_probability_max", [])

    hourly_times = hourly.get("time", [])
    hourly_index = {stamp: i for i, stamp in enumerate(hourly_times)}
    hourly_temp = hourly.get("temperature_2m", [])
    hourly_humidity = hourly.get("relative_humidity_2m", [])
    hourly_wind = hourly.get("wind_speed_10m", [])
    hourly_wind_dir = hourly.get("wind_direction_10m", [])
    hourly_cloud = hourly.get("cloud_cover", [])
    hourly_rain_chance = hourly.get("precipitation_probability", [])
    hourly_precip = hourly.get("precipitation", [])

    def _at(date_str, hour, values):
        index = hourly_index.get(f"{date_str}T{hour:02d}:00")
        if index is None or index >= len(values):
            return None
        value = values[index]
        return None if value is None or value != value else value

    def _daily(values, index):
        if index >= len(values):
            return None
        value = values[index]
        return None if value is None or value != value else value

    def _night_values(date_str, values):
        date = datetime.date.fromisoformat(date_str)
        next_date = (date + datetime.timedelta(days=1)).isoformat()
        values_by_hour = [
            _at(date_str, hour, values) for hour in range(20, 24)
        ] + [
            _at(next_date, hour, values) for hour in range(0, 3)
        ]
        return values_by_hour

    def _longest_wet_run(values, threshold_mm=0.1):
        longest = 0
        current = 0
        for value in values:
            if value is not None and value >= threshold_mm:
                current += 1
                longest = max(longest, current)
            else:
                current = 0
        return longest

    rows = []
    for index, date_str in enumerate(daily_dates):
        date = datetime.date.fromisoformat(date_str)
        phase, moon_name = moon_phase(date)
        temp_c = _at(date_str, 21, hourly_temp)
        wind_kmh = _at(date_str, 21, hourly_wind)
        precip_mm = _daily(daily_precip, index)
        night_rain_chances = [
            value for value in _night_values(date_str, hourly_rain_chance)
            if value is not None
        ]
        night_precip_values = _night_values(date_str, hourly_precip)
        measured_night_precip = [
            value for value in night_precip_values if value is not None
        ]
        rain_chance = (
            max(night_rain_chances) if night_rain_chances
            else _daily(daily_rain_chance, index)
        )
        if rain_chance is None:
            rain_chance = _at(date_str, 21, hourly_rain_chance)
        rows.append({
            "date": date_str,
            "temp_f_9pm": round(_c_to_f(temp_c)) if temp_c is not None else None,
            "humidity_9pm": (
                round(_at(date_str, 21, hourly_humidity))
                if _at(date_str, 21, hourly_humidity) is not None else None
            ),
            "wind_mph_9pm": (
                round(_kmh_to_mph(wind_kmh), 1)
                if wind_kmh is not None else None
            ),
            "wind_dir_9pm": (
                round(_at(date_str, 21, hourly_wind_dir))
                if _at(date_str, 21, hourly_wind_dir) is not None else None
            ),
            "cloud_pct_9pm": (
                round(_at(date_str, 21, hourly_cloud))
                if _at(date_str, 21, hourly_cloud) is not None else None
            ),
            "rain_chance_pct": round(rain_chance) if rain_chance is not None else None,
            "precip_in": (
                round(precip_mm * 0.0393701, 2)
                if precip_mm is not None else None
            ),
            "night_precip_in": (
                round(sum(measured_night_precip) * 0.0393701, 2)
                if measured_night_precip else None
            ),
            "night_peak_precip_in": (
                round(max(measured_night_precip) * 0.0393701, 2)
                if measured_night_precip else None
            ),
            "night_rain_hours": sum(
                value is not None and value >= 0.1
                for value in night_precip_values
            ),
            "night_longest_rain_hours": _longest_wet_run(
                night_precip_values
            ),
            "moon_phase": round(phase, 4),
            "moon": moon_name,
            "moon_illumination_pct": round(moon_illumination(phase) * 100),
        })
    return rows


def _fetch_forecast(days=10):
    """Fetch upcoming nightly conditions from Open-Meteo."""
    params = urllib.parse.urlencode({
        "latitude": PROPERTY_LAT,
        "longitude": PROPERTY_LON,
        "forecast_days": min(days + 1, 16),
        "daily": "precipitation_sum,precipitation_probability_max",
        "hourly": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "wind_speed_10m",
            "wind_direction_10m",
            "cloud_cover",
            "precipitation_probability",
            "precipitation",
        ]),
        "timezone": "America/New_York",
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    })
    with urllib.request.urlopen(
        f"{_OPEN_METEO_FORECAST}?{params}", timeout=30
    ) as response:
        return _forecast_rows(json.loads(response.read()))[:days]


def load_forecast(days=10, refresh=True):
    """Return a resilient upcoming-night forecast with freshness metadata.

    A successful response is cached for later report builds.  If Open-Meteo is
    unavailable, unexpired future rows from the last response remain visible
    and are clearly marked as cached.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    cached = None
    if _FORECAST_CACHE.exists():
        try:
            cached = json.loads(_FORECAST_CACHE.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            cached = None

    cache_age = (
        time.time() - _FORECAST_CACHE.stat().st_mtime
        if cached and _FORECAST_CACHE.exists() else None
    )
    should_fetch = refresh and (
        cached is None
        or cache_age is None
        or cache_age >= _FORECAST_CACHE_TTL_SECONDS
    )

    if should_fetch:
        try:
            nights = _fetch_forecast(days=days)
            cached = {
                "fetched_at": now.isoformat(),
                "nights": nights,
            }
            _FORECAST_CACHE.parent.mkdir(parents=True, exist_ok=True)
            _FORECAST_CACHE.write_text(
                json.dumps(cached, indent=2), encoding="utf-8"
            )
            cache_age = 0
        except Exception as exc:
            print(f"[report-warning] using cached forecast after API error: {exc}")

    if not cached:
        return {
            "fetched_at": None,
            "nights": [],
            "is_stale": True,
            "source": "unavailable",
        }

    today = datetime.date.today().isoformat()
    future = [
        row for row in cached.get("nights", [])
        if row.get("date", "") >= today
    ][:days]
    return {
        "fetched_at": cached.get("fetched_at"),
        "nights": future,
        "is_stale": bool(cache_age is None or cache_age >= 24 * 60 * 60),
        "source": "cache" if cache_age else "live",
    }


def sync_weather(dates):
    """Fetch and cache weather for any dates not yet in weather_cache.

    dates: iterable of datetime.date or date strings.
    """
    if not dates:
        return
    date_strs = sorted({str(d) for d in dates})
    with connect() as conn:
        cached = {r[0] for r in
                  conn.execute("SELECT date FROM weather_cache").fetchall()}
    missing = [d for d in date_strs if d not in cached]
    if not missing:
        print("  weather: all dates cached")
        return
    print(f"  weather: fetching {len(missing)} dates …")
    start = datetime.date.fromisoformat(missing[0])
    end = datetime.date.fromisoformat(missing[-1])
    fetched = _fetch_range(start, end)
    if not fetched:
        return
    rows = []
    for d in missing:
        w = fetched.get(d)
        if not w:
            continue
        frac, _ = moon_phase(datetime.date.fromisoformat(d))
        rows.append((
            d,
            w["temp_f_hi"], w["temp_f_lo"], w["humidity_pct"],
            w["wind_mph"], w["wind_dir_deg"], w["precip_in"],
            round(frac, 4),
            w["temp_f_9pm"], w["humidity_9pm"],
            w["wind_mph_9pm"], w["wind_dir_9pm"],
        ))
    with connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO weather_cache "
            "(date, temp_f_hi, temp_f_lo, humidity_pct, wind_mph, "
            " wind_dir_deg, precip_in, moon_phase, "
            " temp_f_9pm, humidity_9pm, wind_mph_9pm, wind_dir_9pm) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
    print(f"  weather: cached {len(rows)} dates")


def load_weather():
    """Return {date_str: weather_dict} for all cached dates."""
    with connect() as conn:
        rows = conn.execute("SELECT * FROM weather_cache").fetchall()
    out = {}
    for r in rows:
        d = r["date"]
        frac = r["moon_phase"]
        _, mname = moon_phase(datetime.date.fromisoformat(d))
        out[d] = {
            "temp_f_hi": r["temp_f_hi"],
            "temp_f_lo": r["temp_f_lo"],
            "humidity_pct": r["humidity_pct"],
            "wind_mph": r["wind_mph"],
            "wind_dir_deg": r["wind_dir_deg"],
            "precip_in": r["precip_in"],
            "moon": mname,
            "wind_desc": wind_description(r["wind_mph"], r["wind_dir_deg"]),
            "temp_f_9pm": r["temp_f_9pm"],
            "humidity_9pm": r["humidity_9pm"],
            "wind_mph_9pm": r["wind_mph_9pm"],
            "wind_dir_9pm": r["wind_dir_9pm"],
            "wind_desc_9pm": wind_description(r["wind_mph_9pm"], r["wind_dir_9pm"]),
        }
    return out
