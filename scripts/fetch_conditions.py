"""
Pulls current conditions -- primarily from govallecito.com's own live-
conditions backend, with the original independent government-API calls kept
as an automatic fallback if that backend is ever unreachable.

WHY THE WORKER IS THE PRIMARY SOURCE (added 2026-07-24): David's own
Cloudflare Worker (govallecito-conditions.dkontje.workers.dev) already
blends and cross-validates weather (NWS), lake level (USBR RISE), streamflow
(Pine River + Vallecito Creek gauges + dam outflow), fire restriction status
(county + Forest Service, cross-referenced), and real wildfire incident data
(NIFC/WFIGS + NASA FIRMS) -- and govallecito.com's own pages read from it
directly. David asked for "identical reporting" between the site and the
Facebook bot; the most direct way to guarantee that is for both to read the
same numbers from the same place, rather than the bot independently
recomputing similar-but-not-always-identical figures from raw government
APIs. Confirmed live 2026-07-24 (see fetch_worker_snapshot()).

FALLBACK, ON PURPOSE: depending on a single upstream (David's own Worker)
for everything trades away the redundancy of three independent government
data sources. To not make that trade blindly, fetch_weather(),
fetch_streamflow(), and fetch_lake_level() each fall back to the original
direct-API calls (NWS / USGS / Colorado DWR) if the Worker is unreachable OR
its data for that section is stale/malformed. Fire restriction status is the
one exception -- see fetch_fire_status()'s docstring for why that one fails
to "data delayed" instead of a fallback.

Every function here is defensive: if a source is unreachable, times out, or
returns something unrecognized, it returns None instead of raising. The post
generator's job is then to say "data delayed" rather than crash the whole run
or -- worse -- silently carry yesterday's number forward as if it were fresh.
That rule comes straight from the style guide: "Never guess a number... don't
carry yesterday's number forward silently."

fetch_active_alerts() (NWS) is unchanged and still documentation-only (not
exercised against a live response from inside this sandbox) -- see its own
docstring. fetch_lake_level's direct-DWR fallback path was fixed and
confirmed live 2026-07-24 after a real production 400 error; see the big
comment on _fetch_lake_level_from_dwr() below for the story if it ever
breaks again.
"""

import json
import os
from datetime import datetime, timezone

import requests

# ---- location ----------------------------------------------------------
LAT, LON = 37.3856, -107.5217  # Vallecito Lake, CO, near the dam

USER_AGENT = "govallecito-bot/1.0 (govallecito.com daily conditions post; contact@govallecito.com)"
REQUEST_TIMEOUT = 15

# ---- govallecito.com's own live-conditions backend (primary source) -------
# This is David's own Cloudflare Worker -- the same one govallecito.com's own
# pages fetch from (confirmed via that site's network requests, 2026-07-24).
# Unauthenticated, public JSON, no API key needed.
WORKER_CONDITIONS_URL = "https://govallecito-conditions.dkontje.workers.dev/data/conditions.json"
WILDFIRE_RADIUS_MI = 50  # matches the radius the Worker itself already filters wildfire incidents to

# USGS's iv service uses large-magnitude negative sentinels (classically
# -999999) to mean "no data," rather than omitting the value -- parsed as a
# plain float that's indistinguishable from a real (if wildly unusual)
# reading unless checked for explicitly. Only relevant to the direct-USGS
# fallback path now, not the Worker path.
USGS_NO_DATA_SENTINEL_THRESHOLD = -900000

USGS_STREAMFLOW_SITE = "09352900"  # Vallecito Creek near Bayfield
# Confirmed live during development: reporting discharge (parameter 00060)
# every ~15 minutes. Fallback-path only now -- see fetch_streamflow().
#
# NOTE: USGS 09353000 (the reservoir gage itself) is deliberately NOT used --
# confirmed during development that its most recent "approved" reading is
# dated 2012-12-31. It has not reported in over a decade. Don't resurrect it
# as a data source without re-checking it's actually reporting again.

CDSS_STATION_ABBREV = "VALRESCO"  # Colorado DWR telemetry station, Vallecito Reservoir
# Full-pool capacity: matches govallecito.com's own Worker (`capacityAf`,
# sourced from USBR RISE) rather than the previous Wikipedia/USBR-specs
# figure (125,400 AF) this constant used to hold -- confirmed 2026-07-24 via
# a live fetch of the Worker's own conditions.json. Updated here so that even
# the direct-DWR FALLBACK path (used only if the Worker itself is down)
# computes the same percentage the website would show, rather than agreeing
# with the site normally and quietly diverging only during a fallback.
FULL_POOL_CAPACITY_ACRE_FEET = 129_700
FULL_POOL_ELEVATION_FT = 7_665  # matches govallecito.com's own published full-pool figure
# (Wikipedia's infobox lists 7,671 ft for the same thing -- almost certainly a
# vertical-datum difference, NGVD29 vs NAVD88, which is common in this
# region. Deliberately matching the site's own already-published number here
# instead, for internal consistency with what govallecito.com already shows.)


def _get_json(url, headers=None):
    resp = requests.get(url, headers=headers or {}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# ---- shared upstream snapshot ----------------------------------------------

def fetch_worker_snapshot():
    """One HTTP call to govallecito.com's own live-conditions Worker.
    Returns the full parsed JSON dict, or None on any failure (unreachable,
    timeout, non-200, unparseable). fetch_all() calls this ONCE and hands the
    result to each of the section-fetchers below, rather than each of them
    hitting the network independently.

    CONFIRMED LIVE 2026-07-24: fetched directly and inspected the real
    response shape (weather/lake/stream/restriction/wildfire/road/power/
    airQuality/forecast sections, each with its own "status"/"stale" fields).
    """
    try:
        return _get_json(WORKER_CONDITIONS_URL, headers={"User-Agent": USER_AGENT})
    except Exception as exc:
        print(f"[fetch_worker_snapshot] failed: {exc} -- callers will fall back to direct government APIs")
        return None


# ---- weather ----------------------------------------------------------

def _weather_from_snapshot(snapshot):
    w = (snapshot or {}).get("weather") or {}
    if w.get("status") != "ok" or w.get("stale"):
        return None
    current_f = w.get("tempF")
    if current_f is None:
        return None
    # The Worker's own forecast.periods[0] carries an NWS-style period name
    # ("Tonight", "Friday", ...) matching what the old direct-NWS path
    # returned; not load-bearing downstream today (generate_post_text.py
    # doesn't currently use period_name), but kept for parity/future use.
    period_name = "Now"
    try:
        period_name = (snapshot.get("forecast", {}).get("periods") or [{}])[0].get("name") or "Now"
    except Exception:
        pass
    return {
        "current_f": current_f,
        "high_f": w.get("highF"),
        "low_f": w.get("lowF"),
        "short_forecast": w.get("desc") or "",
        "period_name": period_name,
    }


def _fetch_weather_from_nws():
    """Original direct-NWS implementation -- now the fallback path, used
    only if the Worker snapshot is unavailable or its weather section is
    stale/malformed.

    Confirmed against NWS's own documentation (not a live call from this
    sandbox): the /points -> /gridpoints/.../forecast flow, and that a
    descriptive User-Agent is required. Standard, long-stable public API --
    low risk, and it's independent of David's own infrastructure, which is
    the whole point of keeping it as a fallback.

    Assumes it's called during daytime hours (true for our fixed 7am/2pm
    schedule) so periods[0] is a daytime period.
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
        print(f"[fetch_weather] direct-NWS fallback failed: {exc}")
        return None


def fetch_weather(snapshot=None):
    """Returns {"current_f", "high_f", "low_f", "short_forecast", "period_name"}
    or None on failure. Prefers the shared Worker snapshot (pass one in from
    fetch_all() to avoid a redundant fetch); falls back to direct NWS if the
    snapshot is missing or unusable."""
    if snapshot is None:
        snapshot = fetch_worker_snapshot()
    if snapshot:
        result = _weather_from_snapshot(snapshot)
        if result:
            return result
        print("[fetch_weather] Worker snapshot present but weather section missing/stale; falling back to direct NWS")
    return _fetch_weather_from_nws()


# ---- streamflow -------------------------------------------------------

def _streamflow_from_snapshot(snapshot):
    s = (snapshot or {}).get("stream") or {}
    if s.get("status") != "ok" or s.get("stale"):
        return None
    cfs = s.get("combinedCfs")
    if cfs is None:
        return None
    # Deliberately the COMBINED figure (Pine River + Vallecito Creek), not
    # just the single Vallecito Creek gauge the old direct-USGS path reported
    # -- this is what govallecito.com itself surfaces (its Fishing Report
    # text refers to "cfs flowing in" using this same combined number), so
    # matching it is what "identical reporting" actually means here. The
    # "combined" flag lets generate_post_text.py word the caption/row
    # correctly either way (this path vs. the single-gauge USGS fallback
    # below) instead of always claiming "combined" even when a Worker outage
    # quietly switched the actual reading to a single gauge.
    return {"cfs": float(cfs), "timestamp": s.get("asOf"), "combined": True}


def _fetch_streamflow_from_usgs():
    """Original direct-USGS implementation (single gauge: Vallecito Creek) --
    now the fallback path only. Confirmed live during development: site
    09352900 is actively reporting."""
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
        latest = max(values, key=lambda v: v.get("dateTime", ""))
        cfs = float(latest["value"])
        if cfs <= USGS_NO_DATA_SENTINEL_THRESHOLD:
            print(f"[fetch_streamflow] got USGS 'no data' sentinel value ({cfs}); treating as no reading")
            return None
        # combined=False: this is the single Vallecito Creek gauge only (see
        # module docstring) -- generate_post_text.py uses this flag to word
        # the caption/row honestly as "(Vallecito Creek)" rather than
        # claiming the Worker's combined Pine River + Vallecito Creek figure
        # during what is, by definition, a Worker outage.
        return {"cfs": cfs, "timestamp": latest["dateTime"], "combined": False}
    except Exception as exc:
        print(f"[fetch_streamflow] direct-USGS fallback failed: {exc}")
        return None


def fetch_streamflow(snapshot=None):
    """Returns {"cfs", "timestamp", "combined"} or None on failure. Prefers
    the Worker's combined Pine River + Vallecito Creek figure (combined=True);
    falls back to the single Vallecito Creek USGS gauge (combined=False) if
    the Worker is unavailable. generate_post_text.py uses "combined" to word
    the caption/row correctly either way."""
    if snapshot is None:
        snapshot = fetch_worker_snapshot()
    if snapshot:
        result = _streamflow_from_snapshot(snapshot)
        if result:
            return result
        print("[fetch_streamflow] Worker snapshot present but stream section missing/stale; falling back to direct USGS")
    return _fetch_streamflow_from_usgs()


# ---- lake level -------------------------------------------------------

def _lake_level_from_snapshot(snapshot):
    l = (snapshot or {}).get("lake") or {}
    if l.get("status") != "ok" or l.get("stale"):
        return None
    pct_full = l.get("pct")
    if pct_full is None:
        return None
    # Use the Worker's OWN precomputed pct rather than recomputing from
    # storageAf/FULL_POOL_CAPACITY_ACRE_FEET -- the Worker's capacity
    # constant (129,700 AF, USBR RISE) doesn't exactly match this repo's old
    # constant (125,400 AF, Wikipedia/USBR specs), and using the site's own
    # already-computed percentage is what guarantees the number is IDENTICAL
    # to what govallecito.com shows, not just close.
    return {
        "storage_af": l.get("storageAf"),
        "pct_full": round(pct_full),
        "elevation_ft": l.get("elevationFt"),
        "timestamp": l.get("asOf"),
    }


def _fetch_lake_level_from_dwr():
    """Original direct-Colorado-DWR implementation -- now the fallback path,
    used only if the Worker is unreachable or its lake section is
    stale/malformed.

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
        `measDate` / `value` as originally guessed.
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
        print(f"[fetch_lake_level] direct-DWR fallback failed: {exc}")
        return None


def fetch_lake_level(snapshot=None):
    """Returns {"storage_af", "pct_full", "elevation_ft", "timestamp"} or
    None on failure. Prefers the Worker's own precomputed percentage; falls
    back to a direct Colorado DWR query if the Worker is unavailable."""
    if snapshot is None:
        snapshot = fetch_worker_snapshot()
    if snapshot:
        result = _lake_level_from_snapshot(snapshot)
        if result:
            return result
        print("[fetch_lake_level] Worker snapshot present but lake section missing/stale; falling back to direct DWR")
    return _fetch_lake_level_from_dwr()


# ---- fire restriction status + wildfire proximity --------------------------

def _nearby_wildfires_note(wildfire, count):
    """Builds a short, factual, data-only note -- no editorializing about
    whether a fire is "threatening the lake," since this repo has no basis
    to assert that beyond what the source data itself says."""
    if count <= 0:
        return ""
    plural = "s" if count != 1 else ""
    nearest = (wildfire or {}).get("nearest") or {}
    incidents = (wildfire or {}).get("incidents") or []
    nearest_detail = ""
    if nearest.get("name"):
        # Pull containment for the nearest incident specifically, if its
        # record is present in the incidents list.
        match = next((i for i in incidents if i.get("name") == nearest.get("name")), None)
        containment_bit = ""
        if match and match.get("containment") is not None:
            containment_bit = f", {match['containment']}% contained"
        dist = nearest.get("distanceMi")
        dist_bit = f", {dist} mi away" if dist is not None else ""
        nearest_detail = f" -- nearest is {nearest['name']}{dist_bit}{containment_bit}"
    radius = (wildfire or {}).get("radiusMi", WILDFIRE_RADIUS_MI)
    return f"{count} active wildfire{plural} within {radius} mi{nearest_detail}."


def _fire_from_snapshot(snapshot):
    restriction = (snapshot or {}).get("restriction") or {}
    if not restriction:
        return None
    try:
        stage = int(restriction.get("stage") or restriction.get("displayStage") or 0)
    except (TypeError, ValueError):
        stage = 0

    wildfire = (snapshot or {}).get("wildfire") or (snapshot or {}).get("fire") or {}
    count = wildfire.get("count50mi", wildfire.get("count", 0)) or 0
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = 0

    return {
        "stage": stage,
        "stage_label": f"Stage {stage} fire restrictions" if stage else "Fire restrictions",
        # Full restriction.summary is intentionally passed through uncut --
        # generate_post_text.py's existing _condense() already trims it to
        # fit the card, and reusing that (rather than hand-writing a second,
        # shorter summary here) means whatever's shown is always derived
        # directly from the authoritative source text, never editorialized.
        "restrictions_summary": restriction.get("summary") or restriction.get("note") or "",
        "source": restriction.get("issuedBy") or restriction.get("governing") or "La Plata County",
        "source_url": restriction.get("sourceUrl") or restriction.get("source") or restriction.get("url") or "",
        "nearby_wildfires": {
            "count": count,
            "note": _nearby_wildfires_note(wildfire, count),
        },
        "effective_date": restriction.get("effective"),
        "confidence": restriction.get("confidence"),
        # Full passthrough of the raw restriction object, so
        # check_emergency.py's override check can look for whatever
        # override-metadata fields David's Worker adds (overrideHeadline,
        # overrideDetails, overrideCategory, overrideSource,
        # overrideSourceUrl -- see check_emergency.py) without this function
        # needing to know about them in advance.
        "_restriction_raw": restriction,
    }


def fetch_fire_status(snapshot=None):
    """Returns the fire/restriction dict (same shape as before:
    stage/stage_label/restrictions_summary/source/source_url/
    nearby_wildfires), or None if the Worker snapshot is unavailable.

    DELIBERATELY NO FALLBACK to the old hand-maintained config/fire_status.json
    here (that file is no longer read by this function; see its own comment
    if it's still in the repo). Reasoning: fire status has no independent
    live government API of its own -- that was true before this change too,
    which is exactly why a manual file existed in the first place. A file
    nobody is actively updating day-to-day anymore (because the Worker is now
    the primary source) could silently go stale for months and, on the rare
    occasion the Worker has an outage, serve up wildly out-of-date
    restriction info as if it were current. That's a worse failure mode than
    the existing, already-battle-tested "data delayed" path every other
    source in this file already uses on failure -- so a Worker outage means
    fire status is honestly reported as unavailable that cycle, same as a
    weather or lake-level outage would be, rather than silently reusing an
    unmaintained fallback file. If this tradeoff is wrong for how the bot
    actually gets used, it's a one-line change to add a config-file fallback
    back in here.
    """
    if snapshot is None:
        snapshot = fetch_worker_snapshot()
    if not snapshot:
        return None
    result = _fire_from_snapshot(snapshot)
    if not result:
        print("[fetch_fire_status] Worker snapshot present but restriction section missing/empty")
    return result


def fetch_all():
    snapshot = fetch_worker_snapshot()
    return {
        "weather": fetch_weather(snapshot),
        "streamflow": fetch_streamflow(snapshot),
        "lake_level": fetch_lake_level(snapshot),
        "fire": fetch_fire_status(snapshot),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ---- NWS active alerts (flood / fire / evacuation / disaster) -------------
# Unchanged by this update -- independent of David's own Worker on purpose,
# since this is the automated half of emergency detection and shouldn't share
# a single point of failure with the routine daily-post data source.

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

    *** NOT CONFIRMED LIVE *** -- written from NWS's published API docs, not
    exercised against a live response from this sandbox. Run
    scripts/test_data_sources.py or a workflow_dispatch dry run and read the
    raw JSON before fully trusting the field names below.

    KNOWN, DISCLOSED COVERAGE GAP: this only catches alerts NWS itself (or
    another agency relaying through IPAWS) has published. A county-issued
    evacuation notice sent only through La Plata County's own resident
    notification system (LPC Alerts, formerly branded CodeRED -- confirmed
    2026-07-24 that the county migrated systems, and neither the old nor new
    system offers a public API or feed) will NOT appear here. There is no
    free public API for that gap -- see check_emergency.py's manual-override
    checks (both config/emergency_override.json and the Worker's
    restriction.override field) for the two ways David can flag one by hand.
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
                print(f"[fetch_active_alerts] skipping one malformed alert feature: {exc}")
        return alerts
    except Exception as exc:
        print(f"[fetch_active_alerts] failed: {exc}")
        return []


if __name__ == "__main__":
    import pprint
    pprint.pprint(fetch_all())
