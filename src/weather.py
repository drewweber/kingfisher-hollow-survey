"""Weather data for the activity log: Open-Meteo historical API + moon phase."""

import datetime
import time

from config import PROPERTY_LAT, PROPERTY_LON
from db import connect

_OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

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
    """Fetch daily weather from Open-Meteo for a date range.

    Returns {date_str: {temp_f_hi, temp_f_lo, humidity_pct, wind_mph,
                        wind_dir_deg, precip_in}} for each date returned.
    Open-Meteo archive has a ~5-day lag; dates too recent are silently absent.
    """
    import urllib.request
    import json
    import urllib.parse

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

    out = {}
    for i, d in enumerate(dates):
        def _get(lst):
            v = lst[i] if i < len(lst) else None
            return None if v is None or v != v else v  # NaN → None

        hi_c = _get(t_max)
        lo_c = _get(t_min)
        out[d] = {
            "temp_f_hi": round(_c_to_f(hi_c)) if hi_c is not None else None,
            "temp_f_lo": round(_c_to_f(lo_c)) if lo_c is not None else None,
            "humidity_pct": round(_get(hum)) if _get(hum) is not None else None,
            "wind_mph": round(_kmh_to_mph(_get(wspd)), 1) if _get(wspd) is not None else None,
            "wind_dir_deg": round(_get(wdir)) if _get(wdir) is not None else None,
            "precip_in": round(_get(precip) * 0.0393701, 2) if _get(precip) is not None else None,
        }
    return out


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
        ))
    with connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO weather_cache "
            "(date, temp_f_hi, temp_f_lo, humidity_pct, wind_mph, "
            " wind_dir_deg, precip_in, moon_phase) "
            "VALUES (?,?,?,?,?,?,?,?)",
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
        }
    return out
