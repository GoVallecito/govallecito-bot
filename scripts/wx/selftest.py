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
from wx import probe as PROBE           # noqa: E402
from wx import snowline as SL            # noqa: E402
from wx.sources import (caic, cdot, cocorahs, nws, openmeteo,   # noqa: E402
                        snotel, water)

results = {}
FINDINGS = {}


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
    results[name] = {
        "ok": res.ok, "error": res.error, "note": res.age_note,
        "sample": (json.dumps(res.data, default=str)[:400] if res.ok else None),
    }
    return res


def write_markdown(path="state/selftest-latest.md", crash=None):
    """Commit a readable record of this run into the repo.

    GitHub's raw job logs sit behind short-lived signed URLs and the API log
    endpoint needs a token, which makes "just read the log" surprisingly hard
    for anyone or anything not sitting at the browser. A committed markdown
    file is diffable, greppable, readable from a plain clone, and turns the
    weekly scheduled run into a health record you can look back through.
    """
    import datetime as _dt

    ok = [k for k, v in results.items() if v.get("ok")]
    bad = [k for k, v in results.items() if not v.get("ok")]

    L = ["# Self-test — live endpoint check", ""]
    if crash:
        L.append("## The self-test itself crashed")
        L.append("")
        L.append("Everything below may be incomplete. The traceback:")
        L.append("")
        L.append("```")
        L.append(crash.strip())
        L.append("```")
        L.append("")
    L.append(f"Run: {_dt.datetime.now(_dt.timezone.utc).isoformat(timespec='seconds')}")
    L.append(f"Result: **{len(ok)}/{len(results)} sources reachable**")
    L.append("")

    # --- the one that decides whether the product works at all ---
    el = FINDINGS.get("elevation")
    L.append("## The elevation thesis")
    if not el:
        L.append("**NOT EVALUATED** — Open-Meteo did not return usable data.")
    elif el["pass"]:
        L.append("**PASS.** The bands return different forecasts, so the "
                 "elevation parameter is being honoured and elevation-band "
                 "forecasting works.")
    else:
        L.append("**FAIL.** Every band returned the same temperature, which "
                 "means the elevation parameter is being ignored. The "
                 "elevation-band product does not work as designed. Stop and "
                 "investigate before building further.")
    if el:
        L.append("")
        L.append("| Band | Elevation requested (m) | Elevation used (m) | First-hour temp |")
        L.append("|---|---|---|---|")
        for b in C.BANDS:
            k = b["key"]
            L.append(f"| {b['label']} | {b['elevation_m']} | "
                     f"{el['elevations'].get(k, '—')} | {el['temps'].get(k, '—')} |")
    L.append("")

    # --- the zone split this whole product depends on ---
    L.append("## NWS zones")
    zones = FINDINGS.get("zones") or {}
    if zones:
        L.append("| Point | Forecast zone | Fire zone | Grid |")
        L.append("|---|---|---|---|")
        for k, v in zones.items():
            L.append(f"| {k} | {v['forecast_zone']} | {v['fire_zone']} | {v['grid']} |")
        v_zone = (zones.get("vallecito") or {}).get("forecast_zone")
        d_zone = (zones.get("durango") or {}).get("forecast_zone")
        if v_zone and d_zone:
            if v_zone != d_zone:
                L.append("")
                L.append(f"Confirmed: Vallecito ({v_zone}) is in a different "
                         f"forecast zone than Durango ({d_zone}). Polling only "
                         f"one of them would miss the other's warnings.")
            else:
                L.append("")
                L.append(f"**Unexpected:** both points report {v_zone}. The zone "
                         f"constants may need revisiting.")
    else:
        L.append("Not retrieved.")
    L.append("")

    L.append("## Every source")
    L.append("")
    L.append("| Source | OK | Detail |")
    L.append("|---|---|---|")
    for k in sorted(results):
        v = results[k]
        detail = (v.get("error") or v.get("note") or "")
        detail = str(detail).replace("|", "\\|")[:180]
        L.append(f"| {k} | {'yes' if v.get('ok') else 'NO'} | {detail} |")
    L.append("")

    probes = FINDINGS.get("probes")
    if probes and "error" not in probes:
        L.append("## Endpoint probes")
        L.append("")
        L.append("Variants tried against the endpoints that failed. The one that "
                 "returns 200 with real content is the shape the adapter should use.")
        for src, variants in probes.items():
            L.append("")
            L.append(f"### {src}")
            L.append("")
            L.append("| Status | Rows | Variant | First data row |")
            L.append("|---|---|---|")
            for name, r in variants.items():
                head = str(r.get("head") or r.get("error") or "")[:150]
                head = head.replace("|", "\\|").replace("`", "'")
                L.append(f"| {r.get('status')} | {r.get('rows', '-')} | {name} | `{head}` |")
        L.append("")

    if bad:
        L.append("## Needs attention")
        L.append("")
        for k in bad:
            L.append(f"- **{k}** — {results[k].get('error')}")
        L.append("")
        L.append("A failure here is information, not a crash. CDOT without a key "
                 "and CAIC out of season are both expected.")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write("\n".join(L) + "\n")
    print(f"\nWrote {path} — committed by the workflow so it can be read "
          f"without touching GitHub's logs.")


def main():
    check("NWS alerts (COZ019 + COZ022)", nws.fetch_alerts)
    check("NWS AFD (GJT)", lambda: nws.fetch_afd())

    for pt in ("vallecito", "durango"):
        p = C.POINTS[pt]
        r = check(f"NWS gridpoint {pt}", lambda p=p: nws.fetch_point_forecast(p["lat"], p["lon"]))
        if r and r.ok:
            print(f"  >> zone={r.data['forecast_zone']} fire={r.data['fire_zone']} "
                  f"grid={r.data['grid']}")
            FINDINGS.setdefault("zones", {})[pt] = {
                "forecast_zone": r.data["forecast_zone"],
                "fire_zone": r.data["fire_zone"],
                "grid": r.data["grid"],
            }

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
        FINDINGS["elevation"] = {"pass": False, "temps": temps, "elevations": elevations}
    else:
        print(f"  OK: {distinct} distinct band temperatures.")
        results["elevation_thesis"] = {"ok": True, "distinct_temps": distinct}
        FINDINGS["elevation"] = {"pass": True, "temps": temps, "elevations": elevations}

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

    # Probe the two adapters that have never worked live. Cheap, and it turns
    # "it returns 400" into "here is the URL shape that works."
    needs_probe = [k for k in ("Colorado DWR reservoir", "CoCoRaHS reports")
                   if not results.get(k, {}).get("ok", True)]
    if needs_probe:
        print(f"\n{'=' * 66}\nPROBING FAILED ENDPOINTS: {needs_probe}\n{'=' * 66}")
        try:
            FINDINGS["probes"] = PROBE.run_all()
            for src, variants in FINDINGS["probes"].items():
                print(f"\n{src}")
                for name, r in variants.items():
                    print(f"  [{r.get('status')}] {name}")
                    if r.get("head"):
                        print(f"        {r['head'][:160]}")
        except Exception as exc:  # noqa: BLE001
            print(f"probe failed: {exc}")
            FINDINGS["probes"] = {"error": str(exc)}

    os.makedirs("output", exist_ok=True)
    with open("output/selftest.json", "w") as fh:
        json.dump(results, fh, indent=2)
    write_markdown()

    failed = [k for k, v in results.items() if not v.get("ok")]
    print(f"\n{'=' * 66}\nSUMMARY: {len(results) - len(failed)}/{len(results)} ok")
    if failed:
        print("FAILED: " + ", ".join(failed))
    print("=" * 66)
    # Deliberately exits 0 even with failures -- this is a diagnostic you read,
    # not a gate. A red X would just make you skip reading it.
    return 0


if __name__ == "__main__":
    # The whole point of this script is the record it leaves behind, so a crash
    # must still produce one. Without this, an exception anywhere above means
    # the run fails with the reason visible only in a log that is genuinely
    # hard to read after the fact -- which is exactly what happened once.
    try:
        code = main()
    except Exception:
        import traceback
        tb = traceback.format_exc()
        print(tb)
        results["selftest_itself"] = {"ok": False, "error": tb.strip().splitlines()[-1]}
        try:
            write_markdown(crash=tb)
        except Exception as inner:
            print(f"could not even write the result file: {inner}")
        code = 1
    sys.exit(code)
