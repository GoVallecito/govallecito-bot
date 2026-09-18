import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from wx import snowline as SL
from wx import constants as C


def test_missing_freezing_level_returns_none():
    assert SL.snow_line_ft(None) is None


def test_snow_line_is_below_freezing_level():
    r = SL.snow_line_ft(2400, temp_f=34, dew_point_f=32, precip_in_hr=0.05)
    assert r["snow_line_ft"] < r["freezing_level_ft"]


def test_dry_air_pushes_snow_line_lower():
    humid = SL.snow_line_ft(2400, temp_f=34, dew_point_f=33, precip_in_hr=0.05)
    dry = SL.snow_line_ft(2400, temp_f=40, dew_point_f=18, precip_in_hr=0.05)
    assert dry["snow_line_ft"] < humid["snow_line_ft"], "dry air must lower the line"


def test_heavy_precip_pushes_snow_line_lower():
    light = SL.snow_line_ft(2400, temp_f=34, dew_point_f=32, precip_in_hr=0.01)
    heavy = SL.snow_line_ft(2400, temp_f=34, dew_point_f=32, precip_in_hr=0.30)
    assert heavy["snow_line_ft"] < light["snow_line_ft"]


def test_offset_is_clamped():
    absurd = SL.snow_line_ft(2400, temp_f=100, dew_point_f=-40, precip_in_hr=5.0)
    assert absurd["offset_ft"] <= SL.MAX_OFFSET_FT


def test_dry_hours_are_skipped():
    payload = {"hourly": {
        "time": ["2026-11-04T00:00", "2026-11-04T01:00", "2026-11-04T02:00"],
        "freezing_level_height": [2400, 2400, 2350],
        "temperature_2m": [33, 33, 32],
        "dew_point_2m": [31, 31, 31],
        "precipitation": [0.0, 0.05, 0.08],
    }}
    s = SL.series_from_payload(payload)
    assert len(s) == 2, "hours with no precipitation must not produce a snow line"


def test_band_classification_spans_the_real_spread():
    summary = {"representative_ft": 7200}
    cls = SL.classify_bands(summary, C.BANDS)
    assert cls["durango"]["precip_type"] == "rain"
    assert cls["vallecito"]["precip_type"] == "snow"
    assert cls["weminuche"]["precip_type"] == "snow"


def test_transition_band_is_honest():
    summary = {"representative_ft": 6900}
    cls = SL.classify_bands(summary, C.BANDS)
    assert "either way" in cls["bayfield"]["precip_type"]


def test_summarize_detects_falling_line():
    series = [{"snow_line_ft": v, "time": f"h{i}"} for i, v in
              enumerate([8000, 7900, 7800, 7000, 6800, 6700])]
    out = SL.summarize(series)
    assert out["trend"] == "falling"
    assert out["start_ft"] > out["end_ft"]


# --- the 47,200 ft bug -----------------------------------------------------
#
# Open-Meteo returns freezing_level_height in FEET when the request asks for
# fahrenheit/mph/inch, and metres otherwise. Assuming metres against an
# imperial response multiplies every height by 3.28. It produced a 47,200 ft
# snow line in a live run, and in winter it would have been quieter and far
# worse: a real 6,000 ft freezing level becomes 19,685 ft, every band reads as
# rain, and a snowstorm is forecast as a wet day.

def _payload(value, unit):
    return {"hourly_units": {"freezing_level_height": unit},
            "hourly": {"time": ["2026-11-04T00:00"],
                       "freezing_level_height": [value],
                       "temperature_2m": [33], "dew_point_2m": [31],
                       "precipitation": [0.05]}}


def test_units_are_read_from_the_response_not_assumed():
    assert SL.units_of(_payload(7400, "ft")) == "ft"
    assert SL.units_of(_payload(2256, "m")) == "m"


def test_imperial_and_metric_agree():
    ft = SL.series_from_payload(_payload(7400, "ft"))[0]["snow_line_ft"]
    m = SL.series_from_payload(_payload(2256, "m"))[0]["snow_line_ft"]   # 2256 m = 7402 ft
    assert abs(ft - m) <= 10, f"same altitude, different units: {ft} vs {m}"


def test_a_winter_freezing_level_does_not_read_as_rain_everywhere():
    """The failure mode that would have cost the first storm of the season."""
    s = SL.series_from_payload(_payload(6000, "ft"))
    line = SL.summarize(s)["representative_ft"]
    assert line < 6000, "snow line must sit below the freezing level"
    cls = SL.classify_bands({"representative_ft": line}, C.BANDS)
    assert cls["vallecito"]["precip_type"] == "snow", \
        "Vallecito at 7,650 ft must be snow when the freezing level is 6,000 ft"
    assert cls["weminuche"]["precip_type"] == "snow"


def test_implausible_freezing_levels_are_refused():
    for bad in (99000, -50000):
        assert SL.snow_line_ft(bad, 33, 31, 0.05, units="ft") is None
    # and the double-converted value that started this
    assert SL.snow_line_ft(14387 * 3.28084, 33, 31, 0.05, units="ft") is None


def test_result_records_which_unit_it_used():
    r = SL.snow_line_ft(7400, 33, 31, 0.05, units="ft")
    assert r["source_units"] == "ft"


# --- above the terrain it describes ----------------------------------------
#
# Nine straight days in September 2026 reported a snow line of 13,600-14,400 ft
# and two consecutive runs both said 14,050. That looks like a stuck default
# and is not: each was a genuine freezing level minus a genuine melt offset,
# and the repeats come from a 48-hour averaging window overlapping a full day
# between runs inside one monsoon airmass. The math was right. Printing a
# number above the highest peak in the San Juans was the defect.

def _series(value_ft, n=12):
    return [{"snow_line_ft": float(value_ft), "time": f"2026-09-16T{h:02d}:00"}
            for h in range(n)]


def test_a_line_above_the_peaks_is_flagged_not_clamped():
    s = SL.summarize(_series(14050))
    assert s["above_terrain"] is True
    assert s["representative_ft"] == 14050, "the value is kept, only flagged"


def test_an_ordinary_line_is_not_flagged():
    s = SL.summarize(_series(7200))
    assert s["above_terrain"] is False
    assert s["representative_ft"] == 7200


def test_the_ceiling_sits_below_the_peaks_but_above_the_passes():
    # Wolf Creek is about 10,850 and Red Mountain about 11,000; the fourteeners
    # are just over 14,000. The ceiling has to be above the first and below the
    # second or it either gags real forecasts or never fires.
    assert 11500 < SL.TERRAIN_CEILING_FT < 14000
    assert SL.summarize(_series(11000))["above_terrain"] is False


def test_the_headline_and_the_frontmatter_drop_the_figure():
    from wx import site as SITE
    bundle = {"snow_line": {"representative_ft": 14100, "trend": "steady",
                            "above_terrain": True},
              "alerts": [], "generated_at": "2026-09-13T06:51:00",
              "post_for_date": "2026-09-13"}
    title = SITE.auto_title(bundle, "school_call")
    assert "14,100" not in title and "Snow line" not in title
    fm = SITE.front_matter(bundle, "school_call", title)
    assert fm["snowLineFt"] is None
