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

# Overridable for tests; None means resolve from WX_STATE_DIR at call time.
# Derived from __file__ this pointed at the live repo state whatever the
# environment said, which is the same defect that let a test fixture overwrite
# a real draft and, in verify.py, the snow line calibration.
MANUAL_LOG = None


def _manual_log():
    return MANUAL_LOG or os.path.join(
        os.environ.get("WX_STATE_DIR") or "state", "home_gauge.json")

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
    path = _manual_log()
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return (json.load(fh) or {}).get(date)
    except Exception as exc:  # noqa: BLE001
        print(f"[observations] home gauge unreadable: {exc}")
        return None


# A reading is only usable if it is actually from this morning. Past that a
# stale number reads as a live observation, which is the same lie by a slower
# route.
HOME_GAUGE_MAX_AGE_H = 18

# Nobody has snow on a stake at 7,650 ft in July. A depth field in these months
# is a leftover from the spring or a typo, and a post that repeats it is
# exactly the fabrication this is here to stop.
NO_SNOW_MONTHS = (6, 7, 8, 9)
SNOW_DEPTH_FIELDS = ("new_snow_in", "snow_depth_in", "stake_in")
_QUOTABLE_FIELDS = SNOW_DEPTH_FIELDS + ("precip_in", "snow_line_observed_ft")


def read_home_gauge_for_post(post_date_iso, now=None):
    """The reading the post may quote from the gauge or the stake, or None.

    WHY THIS IS NARROWER THAN read_home_gauge. That one serves verification,
    which looks backwards and is happy with any entry it can find. This one
    feeds the composer, which looks at a reader, and a wrong number there is a
    different kind of wrong.

    On 2026-09-17 a draft said the snow stake at the house was "still sitting
    at 5 inches" on an all-rain day with the snow line at 14,000 ft. Nothing
    was behind it: state/home_gauge.json is {} and always has been, and the
    bundle carried no gauge value at all. The persona asks for exactly one
    personal detail and tells the model to rotate which one, so when the
    stake's turn came round the model supplied a plausible figure for it.

    So: today's entry only, not stale, and no snow depth in the months when
    there cannot be any. Returning None is the normal case and the composer is
    told so in as many words, because an absence that is stated does not get
    filled in and an absence that is merely implied does.
    """
    if not post_date_iso:
        return None
    try:
        date = _dt.date.fromisoformat(str(post_date_iso))
    except (TypeError, ValueError):
        return None

    entry = read_home_gauge(date)
    if not isinstance(entry, dict) or not entry:
        return None

    now = now or C.local_now()
    as_of = entry.get("as_of")
    if as_of:
        try:
            stamp = _dt.datetime.fromisoformat(str(as_of))
        except (TypeError, ValueError):
            print(f"[observations] home gauge as_of unreadable ({as_of!r}); "
                  "not quoting the reading")
            return None
        if stamp.tzinfo is None and now.tzinfo is not None:
            stamp = stamp.replace(tzinfo=now.tzinfo)
        elif stamp.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=stamp.tzinfo)
        age_h = (now - stamp).total_seconds() / 3600.0
        if age_h > HOME_GAUGE_MAX_AGE_H or age_h < -1:
            print(f"[observations] home gauge reading is {age_h:.1f}h old; "
                  "not quoting it")
            return None
    # No as_of at all is fine: the entry is keyed by the date it is for, and
    # that key is itself the freshness claim. as_of only ever narrows.

    usable = dict(entry)
    if date.month in NO_SNOW_MONTHS:
        dropped = [k for k in SNOW_DEPTH_FIELDS if usable.get(k) is not None]
        for k in dropped:
            usable.pop(k, None)
        if dropped:
            print(f"[observations] dropped {dropped} from the home gauge: "
                  f"no snow on a stake at 7,650 ft in month {date.month:02d}")

    if not any(usable.get(k) is not None for k in _QUOTABLE_FIELDS):
        return None
    usable["for_date"] = date.isoformat()
    return usable


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
