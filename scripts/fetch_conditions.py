"""
Pulls current conditions from public data sources.

Every function here is defensive: if a source is unreachable, times out, or
returns something unrecognized, it returns None instead of raising. The post
generator's job is then to say "data delayed" rather than crash the whole run
or -- worse -- silently carry yesterday's number forward as if it were fresh.
That rule comes straight from the style guide: "Never guess a number... don't
carry yesterday's number forward silently."

IMPORTANT -- this file could not be exercised against the live internet from
inside the sandbox that wrote it (outbound access there is restricted to a
small allowlist that doesn't include any of these APIs). It has real internet
access once running inside GitHub Actions. Before fully trusting it, run the
workflow once by hand (see README, "workflow_dispatch") and read the job log
-- main.py prints exactly what each source returned, and
scripts/test_data_sources.py dumps the raw responses for debugging.

One source (fetch_active_alerts) is built from documentation only and
flagged accordingly below. fetch_lake_level was also documentation-only
until its first production run (2026-07-24) hit a 400 -- see the big
comment on that function for what the real DWR response looks like and
what was wrong with the original guess. Everything else was confirmed
against a live query during development.
"""

import json
import os
from datetime import datetime, timezone

import requests

# ---- location ----------------------------------------------------------
LAT, LON = 37.3856, -107.5217  # Vallecito Lake, CO, near the dam

USER_AGENT = "govallecito-bot/1.0 (govallecito.com daily conditions post; contact@govallecito.com)"
REQUEST_TIMEOUT = 15

# USGS's iv service uses large-magnitude negative sentinels (classically
# -999999) to mean "no data," rather than omitting the value -- parsed as a
# plain float that's indistinguishable from a real (if wildly unusual)
# reading unless checked for explicitly.
USGS_NO_DATA_SENTINEL_THRESHOLD = -900000

USGS_STREAMFLOW_SITE = "09352900"  # Vallecito Creek near Bayfield
# Confirmed live during development: reporting discharge (parameter 00060)
# every ~15 minutes.
#
# NOTE: USGS 09353000 (the reservoir gage itself) is deliberately NOT used --
# confirmed during development that its most recent "approved" reading is
# dated 2012-12-31. It has not reported in over a decade. Don't resurrect it
# as a data source without re-checking it's actually reporting again.

CDSS_STATION_ABBREV = "VALRESCO"  # Colorado DWR telemetry station, Vallecito Reservoir
FULL_POOL_CAPACITY_ACRE_FEET = 125_400  # Vallecito Dam max capacity (Wikipedia / USBR specs)
FULL_POOL_ELEVATION_FT = 7_665  # matches govallecito.com's own published full-pool figure
# (Wikipedia's infobox lists 7,671 ft for the same thing -- almost certainly a
# vertical-datum difference, NGVD29 vs NAVD88, which is common in this
# region. Deliberately matching the site's own already-published number here
# instead, for internal consistency with what govallecito.com already shows.)


def _get_json(url, headers=None):
    resp = requests.get(url, headers=headers or {}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# ---- NWS forecast --------------------------------------------------------

def fetch_weather():
    """Returns {"current_f", "high_f", "low_f", "short_forecast", "period_name"}
    or None on failure.

    Confirmed against NWS's own documentation (not a live call): the
    /points -> /gridpoints/.../forecast flow, and that a descriptive
    User-Agent is required. Standard, long-stable public API -- low risk.

    Assumes it's called during daytime hours (true for our fixed 7am/2pm
    schedule) so periods[0] is a daytime period; if you add a nighttime
    posting slot later, the current_f/high_f logic below needs a second look.
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"}
    try:
        points = _get_json(f"https://api.weather.gov/points/{LAT},{LON}", headers)
        forecast_url = points["properties"]["forecast"]
        forecast = _get_json(forecast_url, headers)
        periods = forecast["properties"]["periods"]
        if not periods:
            return None

        today = periods[0]
        high_f, low_f = None, None
        for p in periods[:4]:
            if p.get("isDaytime") and high_f is None:
                high_f = p.get("temperature")
            if not p.get("isDaytime") and low_f is None:
                low_f = p.get("temperature")

        current_f = today.get("temperature")
        if current_f is None:
            # NWS does sometimes return a null current temperature -- treat
            # that as a failed fetch rather than a "successful" reading with
            # a hole in the one field callers can't do without.
            print("[fetch_weather] NWS returned a null/missing current temperature; treating as failed fetch")
            return None

        return {
            "current_f": current_f,
            "high_f": high_f,
            "low_f": low_f,
            "short_forecast": today.get("shortForecast", ""),
            "period_name": today.get("name", ""),
        }
    except Exception as exc:
        print(f"[fetch_weather] failed: {exc}")
        return None


# ---- USGS streamflow ------------------------------------------------------

def fetch_streamflow():
    """Returns {"cfs", "timestamp"} or None on failure.

    Confirmed live during development: site 09352900 is actively reporting.
    """
    url = (
        "https://waterservices.usgs.gov/nwis/iv/"
        f"?sites={USGS_STREAMFLOW_SITE}&format=json&parameterCd=00060&siteStatus=all"
    )
    try:
        data = _get_json(url)
        series = data["value"]["timeSeries"]
        if not series:
            return None
        values = series[0]["values"][0]["value"]
        if not values:
            return None
        # Pick by timestamp explicitly rather than trusting array order --
        # USGS's iv service is normally chronological, but relying on that
        # implicitly (values[-1]) rather than checking dateTime directly is
        # an avoidable assumption.
        latest = max(values, key=lambda v: v.get("dateTime", ""))
        cfs = float(latest["value"])
        if cfs <= USGS_NO_DATA_SENTINEL_THRESHOLD:
            print(f"[fetch_streamflow] got USGS 'no data' sentinel value ({cfs}); treating as no reading")
            return None
        return {"cfs": cfs, "timestamp": latest["dateTime"]}
    except Exception as exc:
        print(f"[fetch_streamflow] failed: {exc}")
        return None


# ---- Colorado DWR (CDSS) lake level ---------------------------------------

def fetch_lake_level():
    """Returns {"storage_af", "pct_full", "elevation_ft", "timestamp"} or
    None on failure.

    Talks to Colorado's Division of Water Resources telemetry API rather
    than USGS, because the USGS gage at the reservoir itself is dead (see
    above), and because this is closer to the source govallecito.com itself
    credits ("USBR / USACE").

    *** VERIFIED LIVE 2026-07-24 -- see below if it ever breaks again ***
    The first real run (GitHub Actions run #13, 2026-07-23/24) hit a
    400 Bad Request. Root-caused by querying the endpoint directly
    (outside the sandbox's own restricted network) against the real,
    live DWR API:

      - `min-measurementDate` / `max-measurementDate` (this function's
        original query params) are NOT accepted by this endpoint and
        cause a flat 400 -- confirmed by reproducing the exact same 400
        with those params, and getting a clean 200 with the same
        abbrev/format params once they were removed. Rather than guess
        at yet another spelling for a date-range filter, this function
        now doesn't send one at all: the endpoint's default (no date
        filter) already returns a small window of the most recent
        readings (~3,000 records for this one station), and the
        client-side "pick the max by measDateTime" logic below finds
        the latest reading fine without any server-side date filtering.
      - The real record fields are `measDateTime` and `measValue`, not
        `measDate` / `value` as originally guessed. This would have kept
        fetch_lake_level() silently returning None (or silently picking
        an arbitrary "tied" record instead of the true latest one) even
        after the 400 above was fixed -- there was no live sample to
        catch it at write time.
      - `ResultList` (top-level wrapper) and `parameter` (values seen
        for this station: "STORAGE", "ELEV") were both correct in the
        original guess -- unchanged here.

    If this starts failing again: run scripts/test_data_sources.py (or a
    workflow_dispatch run) and diff the raw JSON's field names against
    what's parsed below.
    """
    url = (
        "https://dwr.state.co.us/Rest/GET/api/v2/telemetrystations/telemetrytimeseriesraw"
        f"?abbrev={CDSS_STATION_ABBREV}"
        "&format=json"
    )
    try:
        data = _get_json(url)
        records = data.get("ResultList") or data.get("resultList") or data.get("results") or []
        if not records:
            return None

        def _param(r):
            return (r.get("parameter") or r.get("measType") or "").upper()

        storage_records = [r for r in records if "STORAGE" in _param(r)]
        elev_records = [r for r in records if "GAGE" in _param(r) or "ELEV" in _param(r)]

        if not storage_records:
            return None

        latest_ts = max(r.get("measDateTime", "") for r in storage_records)
        tied = [r for r in storage_records if r.get("measDateTime", "") == latest_ts]
        if len(tied) > 1 and len({r.get("measValue") for r in tied}) > 1:
            print(f"[fetch_lake_level] warning: {len(tied)} storage records tied on "
                  f"measDateTime={latest_ts!r} with differing values -- picking the last "
                  "one in API response order, which may not be the most authoritative "
                  "reading. Worth checking test_data_sources.py output if this recurs.")
        latest_storage = tied[-1]
        storage_af = float(latest_storage.get("measValue"))
        pct_full = round(100 * storage_af / FULL_POOL_CAPACITY_ACRE_FEET)

        elevation_ft = None
        if elev_records:
            latest_elev = sorted(elev_records, key=lambda r: r.get("measDateTime", ""))[-1]
            try:
                elevation_ft = float(latest_elev.get("measValue"))
            except (TypeError, ValueError):
                print("[fetch_lake_level] elevation reading present but not parseable as a number; omitting elevation only")
                elevation_ft = None

        return {
            "storage_af": storage_af,
            "pct_full": pct_full,
            "elevation_ft": elevation_ft,
            "timestamp": latest_storage.get("measDateTime"),
        }
    except Exception as exc:
        print(f"[fetch_lake_level] failed: {exc}")
        return None


# ---- fire status (manual -- see config/fire_status.json) ------------------

def fetch_fire_status():
    """Fire restriction stage has no public API -- the Forest Service /
    county sheriff post it as text/press releases, not structured data. This
    is intentionally a manually-maintained file, not a live feed. See
    config/fire_status.json and the README section on keeping it current."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "fire_status.json",
    )
    try:
        with open(config_path) as f:
            return json.load(f)
    except Exception as exc:
        print(f"[fetch_fire_status] failed: {exc}")
        return None


def fetch_all():
    return {
        "weather": fetch_weather(),
        "streamflow": fetch_streamflow(),
        "lake_level": fetch_lake_level(),
        "fire": fetch_fire_status(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ---- NWS active alerts (flood / fire / evacuation / disaster) -------------

# NWS/CAP "event" strings mapped to the four categories David asked the
# emergency-alert feature to cover. Deliberately an explicit allowlist
# rather than "any Severe/Extreme alert" -- a blanket severity filter would
# also fire on routine-but-severe weather (Winter Storm Warning, Severe
# Thunderstorm Warning, High Wind Warning) that isn't flood/fire/disaster/
# evacuation, and treating those as emergencies would cheapen the ones that
# actually are. Easy to extend later: add another "NWS event string":
# "category" line -- category must be one of the four keys
# generate_post_text.ALERT_CATEGORY_DISPLAY defines.
ALERT_EVENT_CATEGORIES = {
    # flood
    "Flash Flood Warning": "flood",
    "Flash Flood Emergency": "flood",
    "Flood Warning": "flood",
    "Areal Flood Warning": "flood",
    "Coastal Flood Warning": "flood",
    # fire
    "Red Flag Warning": "fire",
    "Fire Warning": "fire",
    "Fire Weather Warning": "fire",
    "Extreme Fire Danger": "fire",
    # evacuation
    "Evacuation Immediate": "evacuation",
    "Evacuation Watch": "evacuation",
    # disaster / civil emergency catch-all
    "Civil Emergency Message": "disaster",
    "Local Area Emergency": "disaster",
    "Shelter In Place Warning": "disaster",
    "Hazardous Materials Warning": "disaster",
    "Nuclear Power Plant Warning": "disaster",
    "Radiological Hazard Warning": "disaster",
}


def fetch_active_alerts():
    """Returns a list of active NWS/CAP alerts covering Vallecito Lake,
    filtered to ALERT_EVENT_CATEGORIES above. Each item:
    {"id", "event", "category", "headline", "description", "severity",
    "effective", "expires"}. Empty list if none are active or the fetch
    fails -- fails closed, same "never crash, never guess" contract as
    every other fetch_* function in this file.

    Uses point= (the same /alerts/active?point=lat,lon query NWS documents),
    not a fixed zone/county code, so this automatically covers whichever
    NWS zone Vallecito Lake falls in -- same approach as fetch_weather()'s
    /points lookup above.

    *** NOT CONFIRMED LIVE *** -- same caveat as fetch_weather() and the
    other NWS-documentation-only endpoints in this file: written from NWS's
    published API docs, not exercised against a live response (this sandbox
    has no path to api.weather.gov). Run scripts/test_data_sources.py or the
    first workflow_dispatch dry run and read the raw JSON before fully
    trusting the field names below.

    KNOWN, DISCLOSED COVERAGE GAP: this only catches alerts NWS itself (or
    another agency relaying through IPAWS) has published. A county sheriff's
    evacuation order issued only through a local CodeRED/Everbridge system,
    with no IPAWS/WEA relay, will NOT appear here -- there is no free public
    API for that. config/emergency_override.json is the manual backstop for
    exactly that gap; see scripts/check_emergency.py.
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"}
    url = f"https://api.weather.gov/alerts/active?point={LAT},{LON}"
    try:
        data = _get_json(url, headers)
        alerts = []
        for feature in data.get("features", []):
            try:
                props = feature.get("properties", {})
                if props.get("status") != "Actual":
                    continue  # skip Test/Exercise/System/Draft messages
                event = props.get("event", "")
                category = ALERT_EVENT_CATEGORIES.get(event)
                if category is None:
                    continue  # real NWS alert, just not one of our four categories
                alerts.append({
                    "id": props.get("id") or feature.get("id"),
                    "event": event,
                    "category": category,
                    "headline": props.get("headline") or event,
                    "description": props.get("description") or "",
                    "severity": props.get("severity"),
                    "effective": props.get("effective"),
                    "expires": props.get("expires"),
                })
            except Exception as exc:
                # One malformed alert feature shouldn't discard every other
                # real, active alert in the same response -- same
                # isolate-per-item principle used throughout this project
                # (fetch_image.py's candidate loop, check_engagement.py's
                # per-record loops).
                print(f"[fetch_active_alerts] skipping one malformed alert feature: {exc}")
        return alerts
    except Exception as exc:
        print(f"[fetch_active_alerts] failed: {exc}")
        return []


if __name__ == "__main__":
    import pprint
    pprint.pprint(fetch_all())
