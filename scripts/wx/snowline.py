"""
Snow line derivation -- the signature output of this forecaster.

WHY THIS EXISTS
"Snow line in feet" is the one number this audience needs and nobody publishes.
A ~5,000 ft spread lives inside one nominal forecast area: Durango at 6,500,
Bayfield 6,900, Vallecito 7,650, the Weminuche above 10,000. Whether tonight is
rain, slush or eight inches depends entirely on where the line sits, and a
forecast pinned to the airport at 6,689 ft answers that question wrong for
everyone up the Pine.

THE PHYSICS, HONESTLY
Snow does not stop at the freezing level. It falls through it and keeps falling
while it melts, so the snow line sits BELOW the 0 C height. How far below
depends mainly on two things:

  * Humidity. In dry air, falling snow evaporates and cools the air around it
    (wet-bulb effect), driving the snow line down -- sometimes well below the
    freezing level. In saturated air the melting distance is short.
  * Precipitation rate. Heavier precipitation drags the melting level down
    ("dynamic cooling"); a hard burst can drop the snow line 1,000 ft in an hour.

THIS IS A HEURISTIC, AND IT IS LABELLED AS ONE EVERYWHERE IT SURFACES.
The coefficients below are physically reasonable starting values, not tuned
constants. They are meant to be CALIBRATED against the home gauge and the
Vallecito SNOTEL over a season, which is exactly the loop that makes a
hyperlocal forecaster better than a national model rather than just closer to
one. calibration.py records every prediction and its verification so the offset
can be fit from real observations after the first winter.

Until it is calibrated, `confidence` is capped at "low" and the composer is
required to hedge the number. Never present an uncalibrated snow line as
settled.
"""

M_TO_FT = 3.28084

# A freezing level outside this range is not a reading, it is a unit bug or a
# bad value. Publishing one is worse than publishing nothing, because a snow
# line above every band silently turns a snowstorm into "rain everywhere".
PLAUSIBLE_FL_FT = (-1000, 20000)

# Melting distance below the freezing level in saturated air, feet.
BASE_OFFSET_FT = 600.0
# Additional drop per degree F of surface dewpoint depression (dry-air cooling).
DRYNESS_FT_PER_DEG_F = 90.0
# Additional drop for precipitation intensity, feet per inch/hour.
INTENSITY_FT_PER_IN_HR = 2200.0
# Physical bounds. A derived offset outside these means an input is wrong.
MIN_OFFSET_FT = 200.0
MAX_OFFSET_FT = 2500.0


def _f(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def snow_line_ft(freezing_level, temp_f=None, dew_point_f=None,
                 precip_in_hr=None, calibration_offset_ft=0.0, units="m"):
    """One hour's snow line, in feet MSL, with its reasoning attached.

    `units` MUST match what the API actually returned. Open-Meteo reports
    freezing_level_height in FEET when the request asks for fahrenheit/mph/inch,
    and in metres otherwise -- so this is read from the response's own
    hourly_units block rather than assumed. Assuming metres against an imperial
    response multiplies every height by 3.28: a real 6,000 ft freezing level
    becomes 19,685 ft, every band reads as rain, and a snowstorm is forecast as
    a wet day. That happened.

    Returns None if the freezing level is missing or implausible -- the caller
    must then say it doesn't know rather than substitute a guess.
    """
    fl_raw = _f(freezing_level)
    if fl_raw is None:
        return None
    fl_ft = fl_raw * M_TO_FT if str(units).lower().startswith("m") else fl_raw
    if not (PLAUSIBLE_FL_FT[0] <= fl_ft <= PLAUSIBLE_FL_FT[1]):
        return None

    t = _f(temp_f)
    td = _f(dew_point_f)
    rate = _f(precip_in_hr, 0.0) or 0.0

    depression = 0.0
    if t is not None and td is not None:
        depression = max(0.0, t - td)

    offset = (BASE_OFFSET_FT
              + DRYNESS_FT_PER_DEG_F * depression
              + INTENSITY_FT_PER_IN_HR * rate)
    offset = max(MIN_OFFSET_FT, min(MAX_OFFSET_FT, offset))
    offset += calibration_offset_ft

    return {
        "snow_line_ft": int(round(fl_ft - offset)),
        "freezing_level_ft": int(round(fl_ft)),
        "offset_ft": int(round(offset)),
        "dewpoint_depression_f": round(depression, 1),
        "precip_in_hr": round(rate, 3),
        "method": "freezing level minus melting-distance heuristic (UNCALIBRATED)",
        "source_units": units,
    }


def units_of(payload, field="freezing_level_height", default="m"):
    """What unit the API says it used. Never guess this."""
    u = ((payload or {}).get("hourly_units") or {}).get(field)
    return u or default


def series_from_payload(payload, calibration_offset_ft=0.0, hours=48):
    """Hourly snow line across an Open-Meteo payload.

    Only computes a line for hours with measurable precipitation. A snow line
    during dry hours is a meaningless number that invites the composer to state
    it as if it mattered.
    """
    if not payload:
        return []
    h = payload.get("hourly") or {}
    times = h.get("time") or []
    if not times:
        return []
    n = min(hours, len(times))
    fl_units = units_of(payload)

    def col(k):
        v = h.get(k) or []
        return list(v[:n]) + [None] * max(0, n - len(v))

    frz, temp, dew, pcp = col("freezing_level_height"), col("temperature_2m"), \
        col("dew_point_2m"), col("precipitation")

    out = []
    for i in range(n):
        rate = _f(pcp[i], 0.0) or 0.0
        if rate <= 0.001:
            continue
        s = snow_line_ft(frz[i], temp[i], dew[i], rate, calibration_offset_ft,
                         units=fl_units)
        if s:
            s["time"] = times[i]
            out.append(s)
    return out


def summarize(series):
    """Collapse an hourly series into what a post actually says.

    A post says "about 7,200 feet tonight, dropping toward 6,800 by morning" --
    a representative value and a direction, not 48 numbers.
    """
    if not series:
        return None
    vals = [s["snow_line_ft"] for s in series]
    first_third = vals[: max(1, len(vals) // 3)]
    last_third = vals[-max(1, len(vals) // 3):]
    start = sum(first_third) / len(first_third)
    end = sum(last_third) / len(last_third)
    delta = end - start
    if delta < -400:
        trend = "falling"
    elif delta > 400:
        trend = "rising"
    else:
        trend = "steady"
    return {
        "representative_ft": int(round(sum(vals) / len(vals) / 50) * 50),
        "start_ft": int(round(start / 50) * 50),
        "end_ft": int(round(end / 50) * 50),
        "min_ft": min(vals),
        "max_ft": max(vals),
        "trend": trend,
        "hours_with_precip": len(series),
        "first_precip_hour": series[0]["time"],
        "last_precip_hour": series[-1]["time"],
    }


def classify_bands(snow_summary, bands):
    """Precip type per elevation band.

    The transition zone is deliberately wide (+/- 400 ft). A band that sits
    inside it gets "rain/snow line -- could go either way," which is the honest
    answer and the one that protects the forecast when the line is the whole
    ballgame.
    """
    if not snow_summary:
        return {}
    line = snow_summary["representative_ft"]
    out = {}
    for b in bands:
        elev = b["elevation_ft"]
        if elev >= line + 400:
            kind = "snow"
        elif elev <= line - 400:
            kind = "rain"
        else:
            kind = "rain/snow line -- could go either way"
        out[b["key"]] = {
            "label": b["label"],
            "elevation_ft": elev,
            "precip_type": kind,
            "feet_above_snow_line": elev - line,
        }
    return out
