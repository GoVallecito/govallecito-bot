"""
Live endpoint self-test. Run this FIRST, on GitHub Actions, before anything else.

Every weather API is blocked from the sandbox this code was written in, so none
of the adapters have ever spoken to a real server. This script is where that
happens. It calls each source, prints what came back, and tells you plainly
which ones work -- rather than discovering a broken field name at 5:45am on the
morning of the first real storm.

It also settles the two questions research could not:
  * whether Open-Meteo's `elevation` parameter really differentiates the bands
    (if it does not, the entire product thesis fails and you need to know now)
  * which CAIC zone contains Vallecito -- answerable only in season
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wx import constants as C            # noqa: E402
from wx import snowline as SL            # noqa: E402
from wx.sources import (caic, cdot, cocorahs, nws, openmeteo,   # noqa: E402
                        snotel, water)

results = {}


def check(name, fn):
    print(f"\n{'=' * 66}\n{name}\n{'=' * 66}")
    try:
        res = fn()
    except Exception as exc:  # noqa: BLE001
        print(f"  EXCEPTION: {exc}")
        results[name] = {"ok": False, "error": str(exc)}
        return None
    ok = getattr(res, "ok", None)
    if ok is None:
        results[name] = {"ok": True, "note": "no SourceResult"}
        print("  returned:", json.dumps(res, default=str)[:900])
        return res
    print(f"  ok={res.ok}  source={res.source}")
    if res.error:
        print(f"  error: {res.error}")
    if res.age_note:
        print(f"  NOTE: {res.age_note}")
    if res.ok:
        print("  data:", json.dumps(res.data, default=str)[:1200])
    results[name] = {"ok": res.ok, "error": res.error, "note": res.age_note}
    return res


def main():
    check("NWS alerts (COZ019 + COZ022)", nws.fetch_alerts)
    check("NWS AFD (GJT)", lambda: nws.fetch_afd())

    for pt in ("vallecito", "durango"):
        p = C.POINTS[pt]
        r = check(f"NWS gridpoint {pt}", lambda p=p: nws.fetch_point_forecast(p["lat"], p["lon"]))
        if r and r.ok:
            print(f"  >> zone={r.data['forecast_zone']} fire={r.data['fire_zone']} "
                  f"grid={r.data['grid']}")

    # --- the critical one -------------------------------------------------
    print(f"\n{'=' * 66}\nELEVATION PARAMETER -- THE PRODUCT THESIS\n{'=' * 66}")
    elevations, temps = {}, {}
    for band in C.BANDS:
        r = check(f"Open-Meteo {band['key']} @ {band['elevation_ft']}ft",
                  lambda b=band: openmeteo.fetch_band(b, days=2))
        if r and r.ok:
            elevations[band["key"]] = r.data.get("elevation")
            t = (r.data.get("hourly") or {}).get("temperature_2m") or []
            temps[band["key"]] = t[0] if t else None
    print(f"\n  elevations echoed back: {elevations}")
    print(f"  first-hour temps:       {temps}")
    distinct = len({v for v in temps.values() if v is not None})
    if distinct <= 1:
        print("  *** FAIL: bands are not differentiating. The elevation parameter "
              "is being ignored and the entire elevation-band product does not "
              "work. Stop and investigate before going further. ***")
        results["elevation_thesis"] = {"ok": False}
    else:
        print(f"  OK: {distinct} distinct band temperatures.")
        results["elevation_thesis"] = {"ok": True, "distinct_temps": distinct}

    r = check("Open-Meteo model spread",
              lambda: openmeteo.fetch_model_spread(
                  next(b for b in C.BANDS if b["key"] == "vallecito"), days=3)
              .get("ecmwf_ifs025"))
    if r and r.ok:
        s = SL.summarize(SL.series_from_payload(r.data))
        print(f"  derived snow line: {s}")

    check("NRCS SNOTEL", snotel.fetch_stations)
    check("USGS streamflow", water.fetch_streamflow)
    check("Colorado DWR reservoir", water.fetch_reservoir)

    r = check("CoCoRaHS reports", cocorahs.fetch_reports)
    if r and r.ok:
        print("  ranked block as it would print in a totals post:")
        for line in (cocorahs.format_for_post(r.data, limit=6) or "").splitlines():
            print(f"    {line}")

    r = check("CDOT road conditions", cdot.fetch_conditions)
    if r and r.ok:
        print("  pass card:")
        for line in (cdot.format_pass_card(r.data) or "").splitlines():
            print(f"    {line}")
    elif r and "CDOT_API_KEY" in (r.error or ""):
        print("  (expected if you have not got the free key yet -- data.cotrip.org)")

    print(f"\n{'=' * 66}\nCAIC ZONE RESOLUTION\n{'=' * 66}")
    r = check("CAIC zone for Vallecito",
              lambda: caic.resolve_zone(C.VALLECITO["lat"], C.VALLECITO["lon"]))
    if r and r.ok:
        print(f"  >> ANSWER: Vallecito is in {r.data['zone_name']}. "
              "Record this in constants.py.")
    else:
        print("  >> Unresolved. Expected out of season; re-run mid-Nov to mid-Apr.")

    os.makedirs("output", exist_ok=True)
    with open("output/selftest.json", "w") as fh:
        json.dump(results, fh, indent=2)

    failed = [k for k, v in results.items() if not v.get("ok")]
    print(f"\n{'=' * 66}\nSUMMARY: {len(results) - len(failed)}/{len(results)} ok")
    if failed:
        print("FAILED: " + ", ".join(failed))
    print("=" * 66)
    # Deliberately exits 0 even with failures -- this is a diagnostic you read,
    # not a gate. A red X would just make you skip reading it.
    return 0


if __name__ == "__main__":
    sys.exit(main())
