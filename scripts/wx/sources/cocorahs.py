"""
CoCoRaHS adapter -- the ground truth for the totals post.

WHY THIS MATTERS MORE THAN IT LOOKS
About a third of the model persona's output is verification posts, and their
backbone is a ranked list of CoCoRaHS station reports with the station names
copied verbatim, distance-and-bearing suffix and all: "Craig 6.8 W: 1.06\"".
That formatting is not incidental -- it is what makes the post read as a real
observer network rather than a model dump, and it is how contributors see
themselves named. Without this adapter the verify half of the loop cannot run,
and the verify half is the trust engine.

La Plata County stations are numbered CO-LP-##.

*** NOT CONFIRMED LIVE ***
Written from CoCoRaHS' documented export interface. Every weather host is
blocked from the sandbox that wrote this, so the parameter names and the
response shape below have never been exercised against a real server. Run
selftest.py on Actions and read the raw output before trusting it. This is the
same caveat the existing bot carries on its own lake-level parsing, for the
same reason -- stated plainly rather than discovered at 5:45am.
"""

import csv
import datetime as _dt
import io
import re

from .http import SourceResult, get_text

EXPORT = "https://data.cocorahs.org/cocorahs/export/exportreports.aspx"

COUNTY = "LP"      # La Plata
STATE = "CO"
# Neighbouring counties worth including: Archuleta (Pagosa side) and Montezuma
# (Cortez/Mancos). Weather does not stop at a county line and a wider net makes
# the totals list look like a region rather than a village.
NEIGHBOR_COUNTIES = ["AL", "MZ"]


def _params(state, county, start, end, report_type="Daily"):
    return {
        "ReportType": report_type,
        "Format": "CSV",
        "State": state,
        "County": county,
        "ReportDateType": "reportdate",
        "StartDate": start.strftime("%m/%d/%Y"),
        "EndDate": end.strftime("%m/%d/%Y"),
        "TimesInGMT": "False",
    }


def _url(params):
    from urllib.parse import urlencode
    return f"{EXPORT}?{urlencode(params)}"


def _num(v):
    """CoCoRaHS uses 'T' for trace and 'NA'/'M' for missing."""
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "NA", "M", "N/A"):
        return None
    if s.upper() == "T":
        return 0.005          # trace, distinguishable from zero and from missing
    try:
        return float(s)
    except ValueError:
        return None


def _pick(row, *names):
    for n in names:
        for k, v in row.items():
            if k and k.strip().lower().replace(" ", "") == n.lower().replace(" ", ""):
                return v
    return None


def fetch_reports(date=None, counties=None, days=1):
    """Daily precipitation and new-snow reports.

    Returns a list sorted by precipitation descending -- which is the order the
    post prints them in, because the biggest number is the headline.
    """
    date = date or _dt.date.today()
    start = date - _dt.timedelta(days=days - 1)
    counties = counties or [COUNTY] + NEIGHBOR_COUNTIES

    rows, errors, urls = [], [], []
    for county in counties:
        url = _url(_params(STATE, county, start, date))
        urls.append(url)
        try:
            text = get_text(url)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{county}: {exc}")
            continue
        if not text or "<html" in text[:400].lower():
            errors.append(f"{county}: got HTML, not CSV (export params likely wrong)")
            continue
        try:
            for row in csv.DictReader(io.StringIO(text)):
                parsed = _parse_row(row, county)
                if parsed:
                    rows.append(parsed)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{county}: parse failed: {exc}")

    if not rows:
        return SourceResult(False, source="CoCoRaHS", url=urls[0] if urls else EXPORT,
                            error="; ".join(errors) or "no reports returned")

    rows.sort(key=lambda r: (r["precip_in"] is None, -(r["precip_in"] or 0)))
    return SourceResult(True, rows, source="CoCoRaHS", url=urls[0],
                        error="; ".join(errors) if errors else None)


def _parse_row(row, county):
    station = _pick(row, "StationNumber", "StationNum", "Station")
    name = _pick(row, "StationName", "Name")
    if not station and not name:
        return None
    precip = _num(_pick(row, "TotalPrecipAmt", "TotalPrecip", "Precip"))
    snow = _num(_pick(row, "NewSnowDepth", "NewSnow", "SnowfallAmt"))
    swe = _num(_pick(row, "NewSnowSWE", "NewSnowSWEAmt"))
    depth = _num(_pick(row, "TotalSnowDepth", "SnowDepth"))
    if precip is None and snow is None:
        return None
    return {
        "station": (station or "").strip(),
        "name": (name or "").strip(),
        "county": county,
        "date": (_pick(row, "ObservationDate", "ReportDate", "Date") or "").strip(),
        "precip_in": precip,
        "new_snow_in": snow,
        "new_snow_swe_in": swe,
        "snow_depth_in": depth,
        "lat": _num(_pick(row, "Latitude", "Lat")),
        "lon": _num(_pick(row, "Longitude", "Lon")),
    }


def format_for_post(reports, limit=12, field="precip_in"):
    """The exact ranked-pairs block a totals post prints.

    Station names are reproduced verbatim, including the distance-and-bearing
    suffix ("Bayfield 6.0 N"), because that is how the network names them and
    how a local recognizes whose gauge it is.
    """
    have = [r for r in reports if r.get(field) is not None]
    have.sort(key=lambda r: -r[field])
    lines = []
    for r in have[:limit]:
        label = r["name"] or r["station"]
        val = r[field]
        shown = "T" if 0 < val <= 0.005 else f"{val:.2f}"
        lines.append(f"{label}:   {shown}\"")
    return "\n".join(lines)


NEAR_VALLECITO = re.compile(r"\bbayfield|vallecito|gem village|forest lakes\b", re.I)


def local_subset(reports):
    """Reports from our own drainage, for the 'up the Pine' line."""
    return [r for r in reports if NEAR_VALLECITO.search(r.get("name", ""))]
