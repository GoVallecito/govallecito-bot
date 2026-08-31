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
