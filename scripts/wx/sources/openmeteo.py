"""
Open-Meteo adapter -- the engine of the elevation-band forecast.

WHY THIS SOURCE IS THE CENTERPIECE
Open-Meteo takes an `elevation` parameter and re-derives the forecast for that
height instead of the model's own terrain height. This was verified: the same
coordinate requested at 2332 m vs 2900 m returns 16.6 C vs 13.1 C. That single
parameter is what makes "Durango 6,500 / Bayfield 6,900 / Vallecito 7,650 /
Weminuche 10,500" possible from one grid cell. Without it we would need four
separate forecast products and would still be guessing at the lapse rate.

It also needs no API key, exposes ECMWF IFS / GFS / ICON / GEM separately (so
the voice rule "name the model, then say whether you believe it" has real data
behind it), and returns `freezing_level_height` in metres MSL, which is the
raw material for the snow line.
"""

from urllib.parse import urlencode

from .. import constants as C
from .http import SourceResult, get_json

BASE = "https://api.open-meteo.com/v1/forecast"

HOURLY = [
    "temperature_2m", "relative_humidity_2m", "dew_point_2m",
    "precipitation", "snowfall", "snow_depth", "freezing_level_height",
    "wind_speed_10m", "wind_gusts_10m", "wind_direction_10m",
    "cloud_cover", "weather_code", "precipitation_probability",
]
DAILY = [
    "temperature_2m_max", "temperature_2m_min", "precipitation_sum",
    "snowfall_sum", "precipitation_hours", "wind_gusts_10m_max",
    "sunrise", "sunset",
]

# Models requested individually so the composer can see genuine disagreement
# rather than a blended average that hides it. Disagreement IS the uncertainty
# statement in this voice -- "the Euro has the axis over the Weminuche, the GFS
# drags it 60 miles south" -- so a single blended number would remove the most
# characteristic thing the forecaster says.
MODELS = ["ecmwf_ifs025", "gfs_seamless", "icon_seamless", "gem_seamless"]

MODEL_LABELS = {
    "ecmwf_ifs025": "Euro",
    "gfs_seamless": "GFS",
    "icon_seamless": "ICON",
    "gem_seamless": "GEM",
}


def _params(band, days, models=None):
    p = {
        "latitude": band["point"]["lat"],
        "longitude": band["point"]["lon"],
        "elevation": band["elevation_m"],   # the whole point
        "hourly": ",".join(HOURLY),
        "daily": ",".join(DAILY),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": C.TIMEZONE,
        "forecast_days": days,
    }
    if models:
        p["models"] = ",".join(models)
    return p


def fetch_band(band, days=5, models=None):
    """Forecast for one elevation band.

    `band` is an entry from constants.BANDS. Returns the full hourly/daily
    payload plus the elevation Open-Meteo actually used, which is echoed back
    in the response -- worth checking, because if it silently ignored our
    elevation the entire product is broken and every band would read the same.
    """
    url = f"{BASE}?{urlencode(_params(band, days, models))}"
    try:
        data = get_json(url)
        returned_elev = data.get("elevation")
        note = None
        if returned_elev is not None and abs(returned_elev - band["elevation_m"]) > 50:
            # Not fatal, but the forecaster should know its bands may have
            # collapsed toward the model's terrain height.
            note = (f"requested {band['elevation_m']}m, API used {returned_elev}m "
                    f"for {band['key']}")
        return SourceResult(True, data, source=f"Open-Meteo {band['key']}",
                            url=url, age_note=note)
    except Exception as exc:  # noqa: BLE001
        return SourceResult(False, source=f"Open-Meteo {band['key']}",
                            url=url, error=str(exc))


def fetch_all_bands(days=5, bands=None):
    """One fetch per band. Returns {band_key: SourceResult}."""
    bands = bands or C.BANDS
    return {b["key"]: fetch_band(b, days=days) for b in bands}


def fetch_model_spread(band, days=5):
    """The same band from four models, for the disagreement narrative.

    Returns {model_key: SourceResult}. Requested separately rather than as a
    comma-joined multi-model call because Open-Meteo's multi-model response
    suffixes every variable name with the model, which is more brittle to parse
    than four clean payloads and gives no benefit here -- these are cheap calls.
    """
    return {m: fetch_band(band, days=days, models=[m]) for m in MODELS}


def summarize_hourly(payload, hours=48):
    """Condense an Open-Meteo payload into something an LLM can reason over.

    Handing a model 500 hourly rows wastes context and invites it to invent
    patterns. This returns per-6-hour blocks plus the extremes that matter, so
    the composer sees shape and timing rather than noise.
    """
    if not payload:
        return None
    h = payload.get("hourly") or {}
    times = h.get("time") or []
    if not times:
        return None

    n = min(hours, len(times))

    def series(key):
        v = h.get(key) or []
        return [x for x in v[:n]]

    temp = series("temperature_2m")
    snow = series("snowfall")
    precip = series("precipitation")
    frz = series("freezing_level_height")
    gust = series("wind_gusts_10m")
    pop = series("precipitation_probability")

    blocks = []
    for start in range(0, n, 6):
        end = min(start + 6, n)
        def _slice(seq):
            return [x for x in seq[start:end] if x is not None]
        t = _slice(temp); s = _slice(snow); p = _slice(precip)
        f = _slice(frz); g = _slice(gust); pp = _slice(pop)
        blocks.append({
            "from": times[start],
            "to": times[end - 1],
            "temp_f_min": round(min(t), 1) if t else None,
            "temp_f_max": round(max(t), 1) if t else None,
            "snow_in": round(sum(s), 2) if s else 0.0,
            "precip_in": round(sum(p), 2) if p else 0.0,
            "freezing_level_ft_min": round(min(f) * 3.28084) if f else None,
            "freezing_level_ft_max": round(max(f) * 3.28084) if f else None,
            "gust_mph_max": round(max(g)) if g else None,
            "pop_max": max(pp) if pp else None,
        })

    return {
        "elevation_m_used": payload.get("elevation"),
        "blocks": blocks,
        "total_snow_in": round(sum(x for x in snow if x is not None), 2),
        "total_precip_in": round(sum(x for x in precip if x is not None), 2),
        "daily": payload.get("daily"),
    }
