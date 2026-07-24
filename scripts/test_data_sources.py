"""
Standalone debug script -- run this by hand (locally, or as a GitHub Actions
workflow_dispatch run) to check each data source independently and see the
RAW response, not just the parsed result. Nothing in here posts anything.

    python scripts/test_data_sources.py

Since 2026-07-24, weather/streamflow/lake_level/fire_status all try
govallecito.com's own Worker FIRST (see test_worker_snapshot() below for its
raw response) and only fall back to the original direct government APIs if
the Worker is unreachable or that section is stale/malformed -- fire_status
has no fallback at all (see fetch_conditions.fetch_fire_status()'s
docstring). If any of those four ever unexpectedly returns None, or looks
wrong, start with test_worker_snapshot()'s raw dump before assuming a
fallback-path bug.

The DWR/USGS-specific tests below remain useful for diagnosing the fallback
paths themselves -- e.g. if fetch_conditions.fetch_lake_level() ever falls
back AND still returns None, its direct-DWR parsing was originally written
from documentation, not a live test call (see the big comment in
fetch_conditions.py for why), so test_lake_level_raw() is the fastest way to
see what the Colorado DWR API actually sent back and fix the field names.
"""

import json
import sys

import requests

import fetch_conditions as fc


def _divider(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def test_worker_snapshot():
    _divider("govallecito.com's own Worker (govallecito-conditions.dkontje.workers.dev) -- RAW response")
    print(f"GET {fc.WORKER_CONDITIONS_URL}\n")
    try:
        resp = requests.get(fc.WORKER_CONDITIONS_URL, headers={"User-Agent": fc.USER_AGENT}, timeout=15)
        print(f"HTTP {resp.status_code}")
        raw = resp.json()
        print("Top-level keys:", list(raw.keys()))
        # Printed section-by-section (not one giant blob), same reasoning as
        # test_lake_level_raw() below not dumping hundreds of raw records --
        # forecast.periods in particular tends to be long enough to push
        # everything else off the top of a terminal/Actions log.
        for key in raw.keys():
            print(f"\n-- {key} --")
            print(json.dumps(raw[key], indent=2)[:1500])
    except Exception as exc:
        print(f"FAILED: {exc}")

    _divider("Worker snapshot -- as fetch_conditions.fetch_worker_snapshot() sees it")
    snapshot = fc.fetch_worker_snapshot()
    if snapshot:
        print("Reached Worker OK -- weather/streamflow/lake_level/fire below should all be "
              "sourced from this snapshot rather than their fallback paths (fire has no "
              "fallback at all; see fetch_conditions.fetch_fire_status()'s docstring).")
    else:
        print("FAILED -- fetch_weather/streamflow/lake_level will silently use their direct "
              "government-API fallback paths instead, and fetch_fire_status will return None.")


def test_weather():
    _divider("NWS weather (api.weather.gov)")
    result = fc.fetch_weather()
    print("Parsed result:", json.dumps(result, indent=2))


def test_streamflow():
    _divider("USGS streamflow (waterservices.usgs.gov, site 09352900)")
    result = fc.fetch_streamflow()
    print("Parsed result:", json.dumps(result, indent=2))


def test_lake_level_raw():
    _divider("Colorado DWR lake level (dwr.state.co.us) -- RAW response")
    # No date-range params here on purpose -- min-measurementDate/
    # max-measurementDate caused a 400 on the first real run (2026-07-24)
    # and were dropped from fetch_conditions.fetch_lake_level() for the
    # same reason. See the comment on that function for the full story.
    url = (
        "https://dwr.state.co.us/Rest/GET/api/v2/telemetrystations/telemetrytimeseriesraw"
        f"?abbrev={fc.CDSS_STATION_ABBREV}"
        "&format=json"
    )
    print(f"GET {url}\n")
    try:
        resp = requests.get(url, timeout=15)
        print(f"HTTP {resp.status_code}")
        raw = resp.json()
        # Print just the shape + first couple records rather than dumping
        # potentially hundreds of rows.
        print("Top-level keys:", list(raw.keys()))
        records = raw.get("ResultList") or raw.get("resultList") or raw.get("results") or []
        print(f"Record count: {len(records)}")
        if records:
            print("First record (check field names against fetch_lake_level's parsing):")
            print(json.dumps(records[0], indent=2))
            print("\nDistinct 'parameter' values seen:",
                  sorted({(r.get("parameter") or r.get("measType") or "?") for r in records}))
    except Exception as exc:
        print(f"FAILED: {exc}")

    _divider("Colorado DWR lake level -- parsed result (via fetch_conditions)")
    print(json.dumps(fc.fetch_lake_level(), indent=2))


def test_fire_status():
    _divider("Fire status (via Worker restriction/wildfire data -- NO fallback; "
              "see fetch_conditions.fetch_fire_status()'s docstring)")
    print(json.dumps(fc.fetch_fire_status(), indent=2))


if __name__ == "__main__":
    # Each check runs in isolation -- this is a multi-source diagnostic tool,
    # so one source hitting a genuinely unexpected response shape shouldn't
    # take down the other checks along with it and hide their output. (The
    # Worker path IS now exercised against a live response, confirmed
    # 2026-07-24; the NWS active-alerts fetch in check_emergency.py remains
    # the one exception -- see fetch_active_alerts()'s docstring.)
    for test_fn in (test_worker_snapshot, test_weather, test_streamflow, test_lake_level_raw, test_fire_status):
        try:
            test_fn()
        except Exception as exc:
            print(f"\n[test_data_sources] {test_fn.__name__} crashed unexpectedly: {exc}")
            print("Continuing with the remaining checks...")
    print("\nDone. If weather/streamflow/lake_level/fire came back None (or fire status "
          "looks stale), start with the Worker snapshot dump at the top of this output -- "
          "most failures will show up there first. If lake_level specifically falls back to "
          "direct DWR and still comes back None, check the 'Distinct parameter values seen' "
          "line above and adjust the STORAGE/GAGE/ELEV matching in "
          "fetch_conditions.fetch_lake_level() to match what's actually there.")
