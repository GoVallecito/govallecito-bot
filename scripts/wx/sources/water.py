"""
Streamflow (USGS) and reservoir storage (Colorado DWR).

Two corrections to earlier research are encoded here:
  * USGS 09353000, the Vallecito Reservoir gage, is DEAD -- its record ends
    2012-12-31. Storage comes from CDSS instead.
  * USGS 09363000 (Florida River) has been dead since 1960, and 09362800 is
    Lemon Reservoir, not a stream gage. Neither is used.

The CDSS field-name handling below is deliberately forgiving. The existing
bot's own README flags lake-level parsing as its least-tested code, written
from documentation because the sandbox couldn't reach dwr.state.co.us. That is
still true here, so this tries several plausible field spellings and reports
what it actually saw rather than failing silently.
"""

import datetime as _dt

from .. import constants as C
from .http import SourceResult, get_json

USGS_IV = "https://waterservices.usgs.gov/nwis/iv/"
CDSS = ("https://dwr.state.co.us/Rest/GET/api/v2/telemetrystations/"
        "telemetrytimeseriesraw")


def fetch_streamflow(site_keys=None):
    """Instantaneous discharge for our gages. Returns {key: {...}}."""
    site_keys = site_keys or list(C.USGS_SITES.keys())
    ids = [C.USGS_SITES[k]["id"] for k in site_keys]
    url = (f"{USGS_IV}?sites={','.join(ids)}&format=json"
           f"&parameterCd=00060&siteStatus=all")
    try:
        data = get_json(url)
    except Exception as exc:  # noqa: BLE001
        return SourceResult(False, source="USGS NWIS", url=url, error=str(exc))

    by_id = {}
    for series in (data.get("value") or {}).get("timeSeries", []) or []:
        try:
            site_no = series["sourceInfo"]["siteCode"][0]["value"]
            values = series["values"][0]["value"]
            dated = [v for v in values if v.get("value") not in (None, "")]
            if not dated:
                continue
            latest = max(dated, key=lambda v: v.get("dateTime", ""))
            cfs = float(latest["value"])
            if cfs <= C.USGS_NO_DATA_SENTINEL_THRESHOLD:
                continue   # USGS's -999999 "no data" sentinel
            by_id[site_no] = {"cfs": cfs, "timestamp": latest.get("dateTime")}
        except Exception:  # noqa: BLE001 -- one bad series shouldn't kill the rest
            continue

    out = {}
    for key in site_keys:
        meta = C.USGS_SITES[key]
        rec = by_id.get(meta["id"])
        out[key] = {"name": meta["name"], "site": meta["id"],
                    "cfs": rec["cfs"] if rec else None,
                    "timestamp": rec["timestamp"] if rec else None}
    if not any(v["cfs"] is not None for v in out.values()):
        return SourceResult(False, source="USGS NWIS", url=url,
                            error="no discharge values returned")
    return SourceResult(True, out, source="USGS NWIS", url=url)


def _first(record, *names):
    for n in names:
        if n in record and record[n] is not None:
            return record[n]
        for k in record:
            if k.lower() == n.lower() and record[k] is not None:
                return record[k]
    return None


def fetch_reservoir(abbrev=None, days_back=4):
    """Vallecito Reservoir storage and elevation from Colorado DWR."""
    abbrev = abbrev or C.CDSS_VALLECITO
    end = _dt.date.today()
    begin = end - _dt.timedelta(days=days_back)
    url = (f"{CDSS}?abbrev={abbrev}&format=json"
           f"&min-measurementDate={begin.isoformat()}"
           f"&max-measurementDate={end.isoformat()}")
    try:
        data = get_json(url)
    except Exception as exc:  # noqa: BLE001
        return SourceResult(False, source="Colorado DWR (CDSS)", url=url, error=str(exc))

    records = (data.get("ResultList") or data.get("resultList")
               or data.get("results") or [])
    if not records:
        return SourceResult(False, source="Colorado DWR (CDSS)", url=url,
                            error="empty ResultList")

    def param(r):
        return str(_first(r, "parameter", "measType", "parameterName") or "").upper()

    storage = [r for r in records if "STORAGE" in param(r)]
    elev = [r for r in records if "GAGE" in param(r) or "ELEV" in param(r)]

    if not storage:
        seen = sorted({param(r) for r in records})[:8]
        return SourceResult(False, source="Colorado DWR (CDSS)", url=url,
                            error=f"no STORAGE parameter; saw {seen}")

    def when(r):
        return str(_first(r, "measDate", "measDateTime", "date") or "")

    latest = max(storage, key=when)
    try:
        storage_af = float(_first(latest, "value", "measValue"))
    except (TypeError, ValueError):
        return SourceResult(False, source="Colorado DWR (CDSS)", url=url,
                            error="storage value not parseable")

    elevation_ft = None
    if elev:
        try:
            elevation_ft = float(_first(max(elev, key=when), "value", "measValue"))
        except (TypeError, ValueError):
            elevation_ft = None

    return SourceResult(True, {
        "storage_af": storage_af,
        "pct_full": round(100 * storage_af / C.FULL_POOL_CAPACITY_AF),
        "elevation_ft": elevation_ft,
        "full_pool_elevation_ft": C.FULL_POOL_ELEVATION_FT,
        "timestamp": when(latest),
    }, source="Colorado DWR (CDSS)", url=url)
