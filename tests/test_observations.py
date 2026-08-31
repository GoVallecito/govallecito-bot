import datetime as _dt, json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from wx import observations as OB, notify as N, verify as V
from wx.sources import cocorahs as CC
from wx.sources.http import SourceResult

REPORTS = [
    {"name": "Vallecito 2.1 NNE", "station": "CO-LP-9", "precip_in": 1.21,
     "new_snow_in": 14.5, "county": "LP"},
    {"name": "Bayfield 6.0 N", "station": "CO-LP-12", "precip_in": 0.94,
     "new_snow_in": 9.0, "county": "LP"},
    {"name": "Bayfield 1.2 SW", "station": "CO-LP-4", "precip_in": 0.80,
     "new_snow_in": 7.0, "county": "LP"},
    {"name": "Durango 3.5 NE", "station": "CO-LP-3", "precip_in": 0.31,
     "new_snow_in": 4.0, "county": "LP"},
    {"name": "Cortez 8.0 W", "station": "CO-MZ-1", "precip_in": 0.05,
     "new_snow_in": 0.0, "county": "MZ"},
]

FAKE = {
    "cocorahs": lambda date=None: SourceResult(True, REPORTS, source="CoCoRaHS"),
    "snotel": lambda: SourceResult(True, {"vallecito": {
        "name": "Vallecito", "elev_ft": 10740, "swe_in": 4.2,
        "pct_of_median": 105, "snow_depth_in": 18}}, source="NRCS SNOTEL"),
}


def test_stations_map_to_the_right_bands():
    o = OB.collect(fetchers=FAKE)
    assert o["vallecito"]["snow_in"] == 14.5
    assert o["durango"]["snow_in"] == 4.0
    assert o["bayfield"]["station_count"] == 2


def test_bayfield_uses_median_not_max():
    # Two Bayfield stations, 9.0 and 7.0. A forecaster that always quotes the
    # higher gauge is grading its own homework.
    o = OB.collect(fetchers=FAKE)
    assert o["bayfield"]["snow_in"] == 9.0  # median of two -> upper of the pair
    assert o["bayfield"]["snow_in"] <= max(9.0, 7.0)


def test_snotel_lands_in_weminuche_not_vallecito():
    # The Vallecito SNOTEL sits 3,000 ft ABOVE Vallecito Lake. Attributing it to
    # the lake band would bias every verification high, permanently.
    o = OB.collect(fetchers=FAKE)
    assert "snow_depth_in" in o["weminuche"]
    assert "snow_depth_in" not in o.get("vallecito", {})


def test_home_gauge_overrides_and_supplies_the_calibration_point():
    with tempfile.TemporaryDirectory() as d:
        OB.MANUAL_LOG = os.path.join(d, "home_gauge.json")
        today = _dt.date.today().isoformat()
        with open(OB.MANUAL_LOG, "w") as fh:
            json.dump({today: {"new_snow_in": 11.0, "snow_line_observed_ft": 7300,
                               "note": "wind scoured the stake"}}, fh)
        o = OB.collect(fetchers=FAKE)
        assert o["vallecito"]["snow_in"] == 11.0, "home gauge must win"
        assert o["snow_line_observed_ft"] == 7300
        assert any("authoritative" in s for s in o["vallecito"]["sources"])


def test_missing_sources_are_reported_not_swallowed():
    broken = dict(FAKE, cocorahs=lambda date=None: SourceResult(
        False, source="CoCoRaHS", error="export returned HTML"))
    o = OB.collect(fetchers=broken)
    assert any("CoCoRaHS" in m for m in o["_meta"]["missing"])


def test_report_block_is_ranked_and_verbatim():
    block = CC.format_for_post(REPORTS, field="new_snow_in")
    lines = block.splitlines()
    assert lines[0].startswith("Vallecito 2.1 NNE"), "must rank by amount"
    assert "Bayfield 6.0 N" in block, "station names must be verbatim"


def test_trace_is_distinct_from_zero_and_missing():
    assert CC._num("T") == 0.005
    assert CC._num("NA") is None
    assert CC._num("0.00") == 0.0


def test_review_notification_degrades_without_github_context():
    os.environ.pop("GITHUB_REPOSITORY", None)
    os.environ.pop("GITHUB_TOKEN", None)
    r = N.review_requested("draft text here", "review", ["life-safety alert"],
                           {"local_date": "2026-11-04", "snow_line": None}, "school_call")
    assert r["notified"] is False and "GITHUB" in r["reason"]


def test_notification_body_carries_the_draft_and_the_reason():
    body = N._body("11/04/26 5:52am: Morning.", "review", ["burn scar mentioned"],
                   {"local_date": "2026-11-04",
                    "snow_line": {"representative_ft": 7200, "trend": "falling",
                                  "start_ft": 7400, "end_ft": 7000},
                    "alerts": [], "missing": []}, "school_call")
    assert "burn scar mentioned" in body
    assert "11/04/26 5:52am" in body
    assert "7200 ft" in body
