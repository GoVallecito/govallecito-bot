import datetime as _dt, json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from wx import constants as C
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
        # local, not UTC: collect() reads the Mountain Time date
        today = C.local_date().isoformat()
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


# --- what the POST is allowed to quote -------------------------------------
#
# read_home_gauge serves verification, which looks backwards and takes any
# entry it finds. read_home_gauge_for_post serves the composer, which faces a
# reader, so it is deliberately narrower. See its docstring for the 09-17
# draft that made it necessary.

def _with_gauge(entries):
    """Point observations at a scratch home_gauge.json holding `entries`."""
    import contextlib

    @contextlib.contextmanager
    def ctx():
        prev = OB.MANUAL_LOG
        with tempfile.TemporaryDirectory() as d:
            OB.MANUAL_LOG = os.path.join(d, "home_gauge.json")
            with open(OB.MANUAL_LOG, "w", encoding="utf-8") as fh:
                json.dump(entries, fh)
            try:
                yield
            finally:
                OB.MANUAL_LOG = prev
    return ctx()


def test_no_entry_for_today_means_no_reading_to_quote():
    with _with_gauge({}):
        assert OB.read_home_gauge_for_post("2026-11-04") is None
    with _with_gauge({"2026-11-03": {"new_snow_in": 6.0}}):
        assert OB.read_home_gauge_for_post("2026-11-04") is None, \
            "yesterday's reading is not this morning's"


def test_a_reading_for_today_comes_through():
    with _with_gauge({"2026-11-04": {"new_snow_in": 6.5, "precip_in": 0.41}}):
        g = OB.read_home_gauge_for_post("2026-11-04")
        assert g["new_snow_in"] == 6.5 and g["precip_in"] == 0.41
        assert g["for_date"] == "2026-11-04"


def test_a_stale_as_of_is_rejected():
    now = _dt.datetime(2026, 11, 4, 5, 45, tzinfo=C._TZ)
    fresh = (now - _dt.timedelta(hours=9)).isoformat()
    stale = (now - _dt.timedelta(hours=30)).isoformat()
    with _with_gauge({"2026-11-04": {"new_snow_in": 6.5, "as_of": fresh}}):
        assert OB.read_home_gauge_for_post("2026-11-04", now=now) is not None
    with _with_gauge({"2026-11-04": {"new_snow_in": 6.5, "as_of": stale}}):
        assert OB.read_home_gauge_for_post("2026-11-04", now=now) is None


def test_summer_never_has_snow_on_the_stake():
    """Nobody has six inches on a stake at 7,650 ft in July.

    The depth is dropped and the rest of the entry survives, so a real summer
    rain total still reaches the post.
    """
    with _with_gauge({"2026-07-14": {"new_snow_in": 6.0, "precip_in": 0.55}}):
        g = OB.read_home_gauge_for_post("2026-07-14")
        assert "new_snow_in" not in g
        assert g["precip_in"] == 0.55
    with _with_gauge({"2026-07-14": {"new_snow_in": 6.0}}):
        assert OB.read_home_gauge_for_post("2026-07-14") is None, \
            "nothing quotable left once the impossible depth is dropped"
    with _with_gauge({"2026-11-04": {"new_snow_in": 6.0}}):
        assert OB.read_home_gauge_for_post("2026-11-04")["new_snow_in"] == 6.0


def _home(swe, depth):
    return {"name": "Vallecito", "elev_ft": 10880, "swe_in": swe,
            "pct_of_median": None, "snow_depth_in": depth, "temp_f": 38,
            "as_of": "2026-09-19"}


def test_compose_hides_snotel_depth_without_snow_water():
    """2026-09-19 quoted a 4-inch SNOTEL depth in September. No SWE, no snow."""
    from wx import compose as CO
    out = CO.render_bundle({"home_snotel": _home(0.0, 4)})
    assert "No snow on the ground at the SNOTEL" in out
    assert "depth 4in" not in out


def test_compose_keeps_snotel_depth_with_real_snowpack():
    from wx import compose as CO
    out = CO.render_bundle({"home_snotel": _home(6.2, 22)})
    assert "depth 22in" in out
