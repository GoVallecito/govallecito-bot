"""
Endpoint probes for the two adapters that have never worked against a live server.

WHY A PROBE INSTEAD OF A FIX
Neither sandbox can reach these hosts, so the only way to test a change is to
push it and run it on Actions. Guessing one URL variant per cycle would be slow
and would teach us nothing when it failed. This tries every plausible variant in
a single run and reports the HTTP status and the first bytes of each response,
so the correct shape can be read off the results rather than inferred.

Deliberately bounded: a couple of hundred characters per variant. This output
gets committed to the repo, and a diagnostic that dumps megabytes into git is
its own kind of problem.
"""

import datetime as _dt
import urllib.error
import urllib.request
from urllib.parse import urlencode

from . import constants as C

TIMEOUT = 20
SNIP = 240


def _try(url, headers=None):
    hdrs = {"User-Agent": C.USER_AGENT}
    if headers:
        hdrs.update(headers)
    try:
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read(4000).decode("utf-8", "replace")
        lines = [l for l in body.splitlines() if l.strip()]
        # Row count and the first DATA line matter more than the header. A 200
        # with a valid header and nothing under it looks like success and is
        # not, which is exactly what CoCoRaHS did.
        return {"status": resp.status, "len": len(body),
                "rows": max(0, len(lines) - 1),
                "head": (lines[1] if len(lines) > 1 else
                         "(header only, NO DATA ROWS)")[:SNIP]}
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(1200).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            body = ""
        return {"status": exc.code, "error": str(exc),
                "head": body[:SNIP].replace("\n", " | ")}
    except Exception as exc:  # noqa: BLE001
        return {"status": None, "error": str(exc)[:180]}


def probe_cdss():
    """Colorado DWR. The live call returns 400, so the parameter names are wrong.

    CDSS has several telemetry endpoints with different date-parameter
    conventions; these cover the documented shapes.
    """
    end = C.local_date()
    start = end - _dt.timedelta(days=4)
    us = start.strftime("%m/%d/%Y")
    ue = end.strftime("%m/%d/%Y")
    iso_s, iso_e = start.isoformat(), end.isoformat()
    base = "https://dwr.state.co.us/Rest/GET/api/v2/telemetrystations"

    variants = {
        "raw + min/max-measurementDate (current code)":
            f"{base}/telemetrytimeseriesraw/?{urlencode({'format':'json','abbrev':C.CDSS_VALLECITO,'min-measurementDate':iso_s,'max-measurementDate':iso_e})}",
        "raw + parameter=STORAGE + startDate/endDate mm/dd/yyyy":
            f"{base}/telemetrytimeseriesraw/?{urlencode({'format':'json','abbrev':C.CDSS_VALLECITO,'parameter':'STORAGE','startDate':us,'endDate':ue})}",
        "raw + parameter=STORAGE + iso dates":
            f"{base}/telemetrytimeseriesraw/?{urlencode({'format':'json','abbrev':C.CDSS_VALLECITO,'parameter':'STORAGE','startDate':iso_s,'endDate':iso_e})}",
        "day + parameter=STORAGE":
            f"{base}/telemetrytimeseriesday/?{urlencode({'format':'json','abbrev':C.CDSS_VALLECITO,'parameter':'STORAGE','startDate':us,'endDate':ue})}",
        "station metadata only (is the abbrev right?)":
            f"{base}/telemetrystation/?{urlencode({'format':'json','abbrev':C.CDSS_VALLECITO})}",
        "hourly + parameter=STORAGE":
            f"{base}/telemetrytimeserieshour/?{urlencode({'format':'json','abbrev':C.CDSS_VALLECITO,'parameter':'STORAGE','startDate':us,'endDate':ue})}",
    }
    return {k: _try(v) for k, v in variants.items()}


def probe_cocorahs():
    """CoCoRaHS. LP and MZ returned no rows and AL returned a 500.

    Either the export parameters are wrong or the response is not the CSV shape
    the parser expects. Capturing the first bytes settles which.
    """
    end = C.local_date()
    start = end - _dt.timedelta(days=2)
    exp = "https://data.cocorahs.org/cocorahs/export/exportreports.aspx"

    def u(**kw):
        p = {"ReportType": "Daily", "Format": "CSV", "State": "CO",
             "ReportDateType": "reportdate", "TimesInGMT": "False"}
        p.update(kw)
        return f"{exp}?{urlencode(p)}"

    variants = {
        "county=LP, mm/dd/yyyy (current code)":
            u(County="LP", StartDate=start.strftime("%m/%d/%Y"), EndDate=end.strftime("%m/%d/%Y")),
        "county=LP, iso dates":
            u(County="LP", StartDate=start.isoformat(), EndDate=end.isoformat()),
        "state only, no county":
            u(StartDate=start.strftime("%m/%d/%Y"), EndDate=end.strftime("%m/%d/%Y")),
        "county=LP, wider window (7 days)":
            u(County="LP", StartDate=(end - _dt.timedelta(days=7)).strftime("%m/%d/%Y"),
              EndDate=end.strftime("%m/%d/%Y")),
        "XML instead of CSV":
            u(County="LP", Format="XML", StartDate=start.strftime("%m/%d/%Y"),
              EndDate=end.strftime("%m/%d/%Y")),
        "ReportType=DailyPrecipReports":
            u(County="LP", ReportType="DailyPrecipReports",
              StartDate=start.strftime("%m/%d/%Y"), EndDate=end.strftime("%m/%d/%Y")),
    }
    return {k: _try(v) for k, v in variants.items()}


def run_all():
    return {"Colorado DWR (CDSS)": probe_cdss(), "CoCoRaHS": probe_cocorahs()}
