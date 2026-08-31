"""
Assembles what ACTUALLY happened, so yesterday's forecast can be scored.

Three sources, in descending order of trust:

  1. THE HOME GAUGE. A hand-entered reading from the stake at the house on CR
     500. It is one point, but it is the only observation taken at the exact
     elevation the product is named for, by someone who knows whether the wind
     scoured the stake. It wins ties.
  2. SNOTEL. Automated, hourly, reliable -- but at 10,740 ft, which is 3,000 ft
     above Vallecito Lake. It measures the Weminuche band, not the lake band.
     Treating it as "Vallecito's snowfall" would quietly bias every
     verification high, so it maps to the weminuche band here.
  3. CoCoRaHS. Volunteer, once-daily, and the only source with real spatial
     coverage across all three towns.

The band assignment below is the part to get right. A verification is only as
honest as its mapping from "a number somewhere" to "the band I forecast."
"""

import datetime as _dt
import json
import os

from . import constants as C
from .sources import cocorahs, snotel

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANUAL_LOG = os.path.join(REPO_ROOT, "state", "home_gauge.json")

# Which CoCoRaHS station names belong to which forecast band. Matched
# case-insensitively as substrings against the station name.
BAND_STATION_HINTS = {
    "durango": ["durango", "hermosa", "animas"],
    "bayfield": ["bayfield", "gem village", "ignacio", "forest lakes"],
    "vallecito": ["vallecito", "lemon", "florida"],
}


def read_home_gauge(date=None):
    """The hand-entered stake reading, if there is one for this date.

    state/home_gauge.json is a plain object keyed by ISO date:
        {"2026-11-04": {"new_snow_in": 6.5, "precip_in": 0.41,
                        "snow_line_observed_ft": 7300, "note": "wind scoured"}}
    Editing that file and pushing is the whole workflow -- same pattern as the
    hand-maintained fire_status.json the conditions bot already uses.
    """
    date = (date or C.local_date()).isoformat()
    if not os.path.exists(MANUAL_LOG):
        return None
    try:
        with open(MANUAL_LOG) as fh:
            return (json.load(fh) or {}).get(date)
    except Exception as exc:  # noqa: BLE001
        print(f"[observations] home gauge unreadable: {exc}")
        return None


def _band_for_station(name):
    low = (name or "").lower()
    for band, hints in BAND_STATION_HINTS.items():
        if any(h in low for h in hints):
            return band
    return None


def collect(date=None, fetchers=None):
    """Observations shaped for verify.verify_pending().

    Returns {band_key: {"snow_in": x, "precip_in": y, "sources": [...]}} plus a
    top-level snow_line_observed_ft when the home gauge supplied one.
    """
    date = date or C.local_date()
    f = {"cocorahs": cocorahs.fetch_reports, "snotel": snotel.fetch_stations}
    if fetchers:
        f.update(fetchers)

    out = {"_meta": {"date": date.isoformat(), "sources_used": [], "missing": []}}

    # --- CoCoRaHS: spatial coverage across the towns ---
    cc = f["cocorahs"](date=date)
    if cc.ok:
        out["_meta"]["sources_used"].append("CoCoRaHS")
        buckets = {}
        for r in cc.data:
            band = _band_for_station(r.get("name"))
            if not band:
                continue
            buckets.setdefault(band, []).append(r)
        for band, rows in buckets.items():
            snows = [r["new_snow_in"] for r in rows if r.get("new_snow_in") is not None]
            precs = [r["precip_in"] for r in rows if r.get("precip_in") is not None]
            entry = out.setdefault(band, {"sources": []})
            if snows:
                # Median, not max. A totals post that always quotes the single
                # highest gauge in the county is how a forecaster convinces
                # itself it was right.
                entry["snow_in"] = round(sorted(snows)[len(snows) // 2], 1)
            if precs:
                entry["precip_in"] = round(sorted(precs)[len(precs) // 2], 2)
            entry["sources"].append(f"CoCoRaHS ({len(rows)} stations)")
            entry["station_count"] = len(rows)
        out["_cocorahs_reports"] = cc.data
    else:
        out["_meta"]["missing"].append(f"CoCoRaHS: {cc.error}")

    # --- SNOTEL: the high band only. See the docstring. ---
    sn = f["snotel"]()
    if sn.ok:
        out["_meta"]["sources_used"].append("SNOTEL")
        home = sn.data.get(C.HOME_SNOTEL) or {}
        if home.get("snow_depth_in") is not None:
            entry = out.setdefault("weminuche", {"sources": []})
            entry["snow_depth_in"] = home["snow_depth_in"]
            entry["swe_in"] = home.get("swe_in")
            entry["sources"].append(f"{home.get('name')} SNOTEL ({home.get('elev_ft')} ft)")
        out["_snotel"] = sn.data
    else:
        out["_meta"]["missing"].append(f"SNOTEL: {sn.error}")

    # --- the home gauge wins for the vallecito band ---
    gauge = read_home_gauge(date)
    if gauge:
        out["_meta"]["sources_used"].append("home gauge (CR 500)")
        entry = out.setdefault("vallecito", {"sources": []})
        if gauge.get("new_snow_in") is not None:
            entry["snow_in"] = gauge["new_snow_in"]
            entry["sources"].append("home gauge, CR 500 (7,650 ft) -- authoritative")
        if gauge.get("precip_in") is not None:
            entry["precip_in"] = gauge["precip_in"]
        if gauge.get("snow_line_observed_ft") is not None:
            # The single most valuable number in the whole system: it is what
            # calibrates the snow-line heuristic.
            out["snow_line_observed_ft"] = gauge["snow_line_observed_ft"]
        if gauge.get("note"):
            entry["note"] = gauge["note"]

    return out
