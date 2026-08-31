"""
NRCS SNOTEL adapter.

The Vallecito SNOTEL (843, 10,740 ft, continuous since 1985) is the home
station -- the number the forecaster quotes as ground truth and the number the
snow-line heuristic gets calibrated against over a season.

The AWDB REST API does NOT expose a basin index, so percent-of-median for the
San Miguel-Dolores-Animas-San Juan basin is computed here from the member
stations. Locals say "percent of median," never "percent of average"; the
naming in this module reflects that deliberately.
"""

import datetime as _dt
import statistics

from .. import constants as C
from .http import SourceResult, get_json

AWDB = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data"

# WTEQ = snow water equivalent, SNWD = snow depth, PREC = accumulated precip,
# TOBS = observed air temp. WTEQ is the one that matters -- snow depth is
# vanity, water is the water year.
ELEMENTS = ["WTEQ", "SNWD", "PREC", "TOBS"]


def _url(triplets, elements, begin, end, duration="DAILY"):
    return (f"{AWDB}?stationTriplets={','.join(triplets)}"
            f"&elements={','.join(elements)}"
            f"&duration={duration}&beginDate={begin}&endDate={end}"
            f"&periodRef=END&centralTendencyType=MEDIAN&returnFlags=false")


def fetch_stations(keys=None, days_back=10):
    """Current SNOTEL values plus the median for today's date.

    Returns {station_key: {...}} including `pct_of_median`, which is the number
    this audience actually talks about.
    """
    keys = keys or list(C.SNOTEL.keys())
    triplets = [C.SNOTEL[k]["triplet"] for k in keys]
    end = C.local_date()
    begin = end - _dt.timedelta(days=days_back)
    url = _url(triplets, ELEMENTS, begin.isoformat(), end.isoformat())

    try:
        raw = get_json(url)
    except Exception as exc:  # noqa: BLE001
        return SourceResult(False, source="NRCS SNOTEL", url=url, error=str(exc))

    by_triplet = {}
    for entry in raw if isinstance(raw, list) else []:
        trip = entry.get("stationTriplet")
        if not trip:
            continue
        slot = by_triplet.setdefault(trip, {})
        for series in entry.get("data", []) or []:
            el = (series.get("stationElement") or {}).get("elementCode")
            values = series.get("values") or []
            if not el or not values:
                continue
            # Last non-null reading, chosen by date rather than array order.
            dated = [v for v in values if v.get("value") is not None]
            if not dated:
                continue
            latest = max(dated, key=lambda v: v.get("date", ""))
            slot[el] = {"value": latest.get("value"), "date": latest.get("date")}
            med = latest.get("median")
            if med is not None:
                slot[f"{el}_median"] = med

    out = {}
    for key in keys:
        meta = C.SNOTEL[key]
        vals = by_triplet.get(meta["triplet"], {})
        swe = (vals.get("WTEQ") or {}).get("value")
        swe_med = vals.get("WTEQ_median")
        pct = None
        if swe is not None and swe_med:
            try:
                pct = round(100 * float(swe) / float(swe_med))
            except (TypeError, ValueError, ZeroDivisionError):
                pct = None
        out[key] = {
            "name": meta["name"],
            "elev_ft": meta["elev_ft"],
            "triplet": meta["triplet"],
            "swe_in": swe,
            "swe_median_in": swe_med,
            "pct_of_median": pct,
            "snow_depth_in": (vals.get("SNWD") or {}).get("value"),
            "precip_in": (vals.get("PREC") or {}).get("value"),
            "temp_f": (vals.get("TOBS") or {}).get("value"),
            "as_of": (vals.get("WTEQ") or {}).get("date"),
        }

    if not any(v["swe_in"] is not None for v in out.values()):
        return SourceResult(False, source="NRCS SNOTEL", url=url,
                            error="no SWE values returned for any station")
    return SourceResult(True, out, source="NRCS SNOTEL", url=url)


def basin_percent_of_median(stations):
    """Basin index, computed from member stations because AWDB won't give it.

    Uses the MEDIAN of station percentages, not the mean: one station reporting
    a wild value (a buried or malfunctioning pillow, common in spring) would
    drag a mean around, and this number gets quoted in public.
    """
    pcts = [s["pct_of_median"] for s in stations.values()
            if s.get("pct_of_median") is not None]
    if not pcts:
        return None
    return {
        "basin": C.BASIN_NAME,
        "pct_of_median": round(statistics.median(pcts)),
        "station_count": len(pcts),
        "range": [min(pcts), max(pcts)],
        "method": "median of member-station percent-of-median (AWDB exposes no basin index)",
    }
