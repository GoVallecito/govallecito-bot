"""
Pass forecasts for US-550 and US-160.

WHAT THIS IS AND IS NOT
It forecasts what the passes are getting. It never states whether one is open
or closed, because we have no live source for that -- CDOT's public feed
documentation has been withdrawn. Asserting a closure we cannot verify is worse
than saying nothing: a wrong "closed" sends someone on a three-hour detour, and
a wrong "open" sends them at a pass that is actually shut. guardrails.py
enforces this, so the rule survives a persuasive-sounding draft.

The local convention matters and is encoded here: the three US-550 passes close
as a UNIT, and "the pass is closed" unqualified means Red Mountain in Durango
and Wolf Creek in Bayfield or Pagosa. Naming the wrong one is an instant tell.
"""

from . import constants as C
from .sources import openmeteo
from .sources.http import SourceResult

# Snow totals at which a pass is worth leading with, in inches over the window.
NOTABLE_IN = 3.0
SIGNIFICANT_IN = 8.0
# Gusts that make a high pass genuinely unpleasant regardless of snow.
WINDY_MPH = 40


def fetch(days=2, fetch_band=None):
    """Forecast every pass. Returns {pass_key: {...}} inside a SourceResult."""
    fetch_band = fetch_band or openmeteo.fetch_band
    out, errors = {}, []
    for p in C.PASSES:
        band = {"key": p["key"], "elevation_m": p["elevation_m"],
                "point": {"lat": p["lat"], "lon": p["lon"], "name": p["name"]}}
        res = fetch_band(band, days=days)
        if not res.ok:
            errors.append(f"{p['name']}: {res.error}")
            continue
        s = openmeteo.summarize_hourly(res.data, hours=days * 24)
        if not s:
            errors.append(f"{p['name']}: no hourly data")
            continue
        gusts = [b["gust_mph_max"] for b in s["blocks"] if b.get("gust_mph_max")]
        temps = [b["temp_f_min"] for b in s["blocks"] if b.get("temp_f_min") is not None]
        out[p["key"]] = {
            "name": p["name"],
            "route": p["route"],
            "elevation_ft": p["elevation_ft"],
            "terrain_m_used": s.get("elevation_m_used"),
            "snow_in": s["total_snow_in"],
            "precip_in": s["total_precip_in"],
            "gust_mph_max": max(gusts) if gusts else None,
            "temp_f_min": min(temps) if temps else None,
        }
    if not out:
        return SourceResult(False, source="Pass forecast (Open-Meteo)",
                            error="; ".join(errors) or "no passes returned")
    return SourceResult(True, out, source="Pass forecast (Open-Meteo)",
                        error="; ".join(errors) if errors else None)


def _phrase(p):
    snow, gust = p["snow_in"], p.get("gust_mph_max")
    bits = []
    if snow >= SIGNIFICANT_IN:
        lo, hi = round(snow * 0.7), round(snow * 1.3)
        bits.append(f"{lo}-{hi}\" of snow")
    elif snow >= NOTABLE_IN:
        bits.append(f"{round(snow * 0.6)}-{round(snow * 1.2)}\" of snow")
    elif snow >= 0.5:
        bits.append("a couple inches at most")
    elif p["precip_in"] >= 0.05:
        bits.append("wet, mostly rain at pass level")
    else:
        bits.append("dry")
    if gust and gust >= WINDY_MPH:
        bits.append(f"gusts to {round(gust)}")
    return ", ".join(bits)


def format_card(passes):
    """The recurring block. Forecast only, with the local conventions intact."""
    if not passes:
        return None
    lines = []

    unit = [passes[k] for k in C.US550_UNIT if k in passes]
    if unit:
        worst = max(unit, key=lambda p: p["snow_in"])
        lines.append(f"US-550 north — Coal Bank, Molas and Red Mountain "
                     f"(they close as a unit): {_phrase(worst)} up high.")
        for p in unit:
            lines.append(f"    {p['name']}, {p['elevation_ft']:,} ft: {_phrase(p)}")

    wolf = passes.get("wolf_creek")
    if wolf:
        lines.append(f"US-160 east — {wolf['name']}, {wolf['elevation_ft']:,} ft: "
                     f"{_phrase(wolf)}.")

    lines.append("")
    lines.append(f"That is the forecast, not the road status. Current closures "
                 f"and chain law: {C.CDOT_STATUS_URL}")
    return "\n".join(lines)


def worth_leading_with(passes):
    """True when a pass is getting enough to belong near the top of a post."""
    return any(p["snow_in"] >= SIGNIFICANT_IN for p in (passes or {}).values())
