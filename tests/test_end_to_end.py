"""
Full pipeline, offline. No network, no API key, no Facebook.

This is the test that has to keep passing, because everything it exercises --
elevation bands, snow line, model disagreement, guardrails, the dead-man
switch, the verify loop -- is what separates this from a script that prints
model output.
"""
import json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from wx import constants as C
from wx import bundle as B, compose as CO, constants as C
from wx import guardrails as G, publish as P, snowline as SL, verify as V
from wx.sources.http import SourceResult

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
PAYLOAD = json.load(open(os.path.join(FIX, "openmeteo_vallecito.json")))


def _scaled(band):
    """Same shape as the fixture, shifted by elevation so bands actually differ."""
    p = json.loads(json.dumps(PAYLOAD))
    p["elevation"] = band["elevation_m"]
    dm = band["elevation_m"] - 2332
    lapse_f = -(dm * 3.28084 / 1000.0) * 3.5      # ~3.5F per 1000ft
    p["hourly"]["temperature_2m"] = [t + lapse_f for t in p["hourly"]["temperature_2m"]]
    p["hourly"]["dew_point_2m"] = [t + lapse_f for t in p["hourly"]["dew_point_2m"]]
    factor = max(0.0, 1 + dm / 3000.0)
    p["hourly"]["snowfall"] = [s * factor for s in p["hourly"]["snowfall"]]
    return p


def fake_fetchers(*, break_band=None, life_safety=False, snotel_ok=True):
    def alerts():
        data = []
        if life_safety:
            data = [{"id": "x1", "event": "Winter Storm Warning",
                     "headline": "Winter Storm Warning until 11 AM",
                     "description": "", "instruction": "", "severity": "Severe",
                     "urgency": "Expected", "onset": None, "expires": None,
                     "sender": "NWS Grand Junction", "life_safety": True,
                     "zones": [C.ZONE_VALLECITO]}]
        return SourceResult(True, data, source="NWS alerts")

    def bands(days=5):
        out = {}
        for b in C.BANDS:
            if break_band and b["key"] == break_band:
                out[b["key"]] = SourceResult(False, source="Open-Meteo",
                                             error="simulated outage")
            else:
                out[b["key"]] = SourceResult(True, _scaled(b), source="Open-Meteo")
        return out

    def spread(band, days=5):
        mult = {"ecmwf_ifs025": 1.0, "gfs_seamless": 0.35,
                "icon_seamless": 0.9, "gem_seamless": 1.1}
        out = {}
        for m, k in mult.items():
            p = json.loads(json.dumps(PAYLOAD))
            p["hourly"]["snowfall"] = [s * k for s in p["hourly"]["snowfall"]]
            out[m] = SourceResult(True, p, source=m)
        return out

    def snotel_f():
        if not snotel_ok:
            return SourceResult(False, source="NRCS SNOTEL", error="simulated outage")
        return SourceResult(True, {
            "vallecito": {"name": "Vallecito", "elev_ft": 10740, "triplet": "843:CO:SNTL",
                          "swe_in": 4.2, "swe_median_in": 4.0, "pct_of_median": 105,
                          "snow_depth_in": 18, "precip_in": 6.1, "temp_f": 24,
                          "as_of": "2026-11-04"},
            "wolf_creek": {"name": "Wolf Creek Summit", "elev_ft": 11000,
                           "triplet": "874:CO:SNTL", "swe_in": 7.9, "swe_median_in": 6.8,
                           "pct_of_median": 116, "snow_depth_in": 31, "precip_in": 9.9,
                           "temp_f": 19, "as_of": "2026-11-04"},
        }, source="NRCS SNOTEL")

    return {
        "alerts": alerts,
        "afd": lambda: SourceResult(True, {"issued": "2026-11-04T04:10:00Z",
                                           "text": ".SHORT TERM...\nA cutoff low.\n"},
                                    source="NWS GJT AFD"),
        "bands": bands, "spread": spread, "snotel": snotel_f,
        "flow": lambda: SourceResult(True, {"animas_durango": {
            "name": "Animas River at Durango", "site": "09361500",
            "cfs": 312.0, "timestamp": "2026-11-04T05:00"}}, source="USGS NWIS"),
        "reservoir": lambda: SourceResult(True, {
            "storage_af": 71000, "pct_full": 57, "elevation_ft": 7649.2,
            "full_pool_elevation_ft": 7665, "timestamp": "2026-11-03"},
            source="Colorado DWR (CDSS)"),
        "caic": lambda lat, lon: SourceResult(False, source="CAIC map-layer",
                                              error="out of season"),
    }


def test_bundle_builds_and_bands_differ():
    b = B.build(fetchers=fake_fetchers())
    assert set(b["bands"]) == set(C.BAND_ORDER)
    snow = {k: b["bands"][k]["summary"]["total_snow_in"] for k in C.BAND_ORDER}
    assert snow["weminuche"] > snow["vallecito"] > snow["durango"], snow


def test_elevation_actually_reached_the_api():
    b = B.build(fetchers=fake_fetchers())
    assert b["bands"]["vallecito"]["summary"]["elevation_m_used"] == 2332
    assert b["bands"]["weminuche"]["summary"]["elevation_m_used"] == 3200


def test_snow_line_and_band_classification_present():
    b = B.build(fetchers=fake_fetchers())
    assert b["snow_line"]["representative_ft"] > 0
    types = b["precip_type_by_band"]
    assert set(types) == set(C.BAND_ORDER)
    assert types["weminuche"]["precip_type"] == "snow"


def test_model_disagreement_is_detected_not_averaged():
    b = B.build(fetchers=fake_fetchers())
    d = b["model_disagreement"]
    assert d["level"] in ("moderate", "wide")
    assert d["low_model"] == "GFS"
    assert set(d["all"]) == {"Euro", "GFS", "ICON", "GEM"}


def test_basin_percent_of_median_computed():
    b = B.build(fetchers=fake_fetchers())
    assert b["basin"]["pct_of_median"] in range(100, 120)


def test_missing_sources_are_named_not_hidden():
    b = B.build(fetchers=fake_fetchers(snotel_ok=False))
    assert "snotel" in b["missing"]
    brief = CO.render_bundle(b)
    assert "DATA YOU DO NOT HAVE TODAY" in brief and "snotel" in brief


def test_dead_man_switch_aborts_on_missing_band():
    b = B.build(fetchers=fake_fetchers(break_band="vallecito"))
    problems = G.require_or_abort(b)
    assert problems and any("vallecito" in p for p in problems)


def test_brief_flags_zone_specific_alerts():
    b = B.build(fetchers=fake_fetchers(life_safety=True))
    brief = CO.render_bundle(b)
    assert "COZ019 ONLY" in brief, "must tell the model Vallecito differs from Durango"


def test_messages_include_persona_and_data():
    b = B.build(fetchers=fake_fetchers())
    msgs = CO.build_messages(b, post_type="school_call")
    system, user = msgs[0]["content"], msgs[1]["content"]
    assert "fluh-REE-duh" in system
    assert "never claim a degree" in system.lower()
    assert "SNOW LINE" in user and "FORECAST BY ELEVATION BAND" in user
    assert "districts decide by 6:30" in user


def test_full_run_publishes_when_clean(monkeypatch=None):
    from wx import run_forecast as RF
    os.environ["DRY_RUN"] = "true"
    b = B.build(fetchers=fake_fetchers())
    draft = ("11/04/26 5:52am: Morning, its Wednesday. Snow line sitting around "
             "7,200ft and falling. Take that with a grain of salt (its been "
             "running low all night). Durango and the Valley are just wet. Up "
             "the Pine its slushy on the 501. Vallecito and the Florida picked "
             "up a few inches and the 240 will be the slick one. The districts "
             "decide by 6:30. At the house I have got about three inches on the "
             "stake. How is it looking out your window?")
    verdict, reasons = G.evaluate(b, draft, first_30_days=False, calibrated=False)
    assert verdict == G.PASS, reasons
    with tempfile.TemporaryDirectory() as d:
        path = P.write_site_post(draft, b, d)
        body = open(path).read()
        assert body.startswith("---") and "snowLineFt" in body
        assert "govallecito-wx" in body


def test_verify_loop_scores_and_calibrates():
    with tempfile.TemporaryDirectory() as d:
        V.FORECAST_LOG = os.path.join(d, "forecast_log.json")
        V.CALIBRATION = os.path.join(d, "cal.json")
        b = B.build(fetchers=fake_fetchers())
        import datetime as _dt
        # local, not UTC -- the code under test now reasons in Mountain Time
        b["local_date"] = (C.local_date() - _dt.timedelta(days=1)).isoformat()
        V.record_forecast(b, {"vallecito": {"snow_low_in": 3.0, "snow_high_in": 7.0}})
        scored = V.verify_pending({"vallecito": {"snow_in": 9.5},
                                   "snow_line_observed_ft": 7600})
        assert len(scored) == 1
        s = scored[0]["score"]["per_band"]["vallecito"]
        assert s["direction"] == "under-forecast" and s["miss_in"] == 2.5
        cal = V.update_calibration()
        assert cal["active"] is False, "must not calibrate off one event"
        assert V.track_record()["verified_events"] == 1
