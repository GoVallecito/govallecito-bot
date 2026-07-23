"""
Standalone debug script -- run this by hand (locally, or as a GitHub Actions
workflow_dispatch run) to check each data source independently and see the
RAW response, not just the parsed result. Nothing in here posts anything.

    python scripts/test_data_sources.py

Use this if fetch_conditions.fetch_lake_level() ever starts returning None --
its parsing was written from documentation, not a live test call (see the
big comment in fetch_conditions.py for why), so this is the fastest way to
see what the Colorado DWR API actually sent back and fix the field names.
"""

import json
import sys
from datetime import date, timedelta

import requests

import fetch_conditions as fc


def _divider(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


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
    today = date.today()
    start = today - timedelta(days=3)
    url = (
        "https://dwr.state.co.us/Rest/GET/api/v2/telemetrystations/telemetrytimeseriesraw"
        f"?abbrev={fc.CDSS_STATION_ABBREV}"
        f"&min-measurementDate={start.isoformat()}&max-measurementDate={today.isoformat()}"
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
    _divider("Fire status (local config/fire_status.json)")
    print(json.dumps(fc.fetch_fire_status(), indent=2))


if __name__ == "__main__":
    # Each check runs in isolation -- this is a multi-source diagnostic tool,
    # so one source hitting a genuinely unexpected response shape (this
    # sandbox can't reach any of these APIs live, so none of this has been
    # exercised against a real response) shouldn't take down the other three
    # checks along with it and hide their output.
    for test_fn in (test_weather, test_streamflow, test_lake_level_raw, test_fire_status):
        try:
            test_fn()
        except Exception as exc:
            print(f"\n[test_data_sources] {test_fn.__name__} crashed unexpectedly: {exc}")
            print("Continuing with the remaining checks...")
    print("\nDone. If lake_level came back None, check the 'Distinct parameter values "
          "seen' line above and adjust the STORAGE/GAGE/ELEV matching in "
          "fetch_conditions.fetch_lake_level() to match what's actually there.")
