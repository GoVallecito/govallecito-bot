"""
Model disagreement is judged on liquid AND snow, never snow alone.

2026-09-25: four models, 0.54-0.93in of rain at Vallecito, 0.0in of snow. The
brief said "none -- all models dry" next to a band forecast of 0.79in, because
_disagreement() only looked at snowfall and September has none. The writer
invented a Euro-versus-the-rest split to reconcile the two lines, and the review
panel rejected the result three rounds running. Every rain-only day had the same
flaw; the one existing test used a snowy fixture, where snow and liquid happen
to move together.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))

from test_end_to_end import PAYLOAD, fake_fetchers
from wx import bundle as B
from wx import compose as CO
from wx.sources.http import SourceResult


def spread(liquid, snow=None):
    """The model_spread shape bundle.build() produces."""
    snow = snow or {m: 0.0 for m in liquid}
    return {m: {"total_precip_in": liquid[m], "total_snow_in": snow[m]}
            for m in liquid}


SEP_25 = {"Euro": 0.93, "GFS": 0.79, "ICON": 0.73, "GEM": 0.54}


# --- the rain day that broke the panel ---------------------------------------

def test_rain_day_is_not_reported_as_dry():
    d = B._disagreement(spread(SEP_25))
    assert d["level"] != "none -- all models dry"
    assert d["level"] == "moderate"
    assert d["basis"] == "liquid"
    assert (d["low_model"], d["low_in"]) == ("GEM", 0.54)
    assert (d["high_model"], d["high_in"]) == ("Euro", 0.93)
    assert d["all_liquid"] == SEP_25
    assert set(d["all_snow"].values()) == {0.0}


def test_models_that_agree_on_rain_are_tight_not_dry():
    d = B._disagreement(spread({"Euro": 0.80, "GFS": 0.79, "ICON": 0.78, "GEM": 0.81}))
    assert d["level"] == "tight"


def test_genuinely_dry_is_still_dry():
    d = B._disagreement(spread({"Euro": 0.0, "GFS": 0.02, "ICON": 0.0, "GEM": 0.05}))
    assert d["level"] == "none -- all models dry"


def test_one_wet_model_against_three_dry_is_wide():
    d = B._disagreement(spread({"Euro": 0.79, "GFS": 0.0, "ICON": 0.0, "GEM": 0.0}))
    assert d["level"] == "wide"
    assert d["high_model"] == "Euro"


# --- snow versus liquid --------------------------------------------------------

def test_models_agree_on_liquid_but_split_on_snow_is_judged_on_snow():
    """The snow line is the whole ballgame: same water, very different day."""
    liquid = {"Euro": 0.60, "GFS": 0.60, "ICON": 0.60, "GEM": 0.60}
    snow = {"Euro": 6.0, "GFS": 0.5, "ICON": 5.0, "GEM": 6.5}
    d = B._disagreement(spread(liquid, snow))
    assert d["basis"] == "snow"
    assert d["level"] == "wide"
    assert d["low_model"] == "GFS"
    # Both totals are still carried, so the writer sees the whole picture.
    assert d["all_liquid"] == liquid and d["all_snow"] == snow


def test_liquid_wins_a_tie():
    liquid = {"Euro": 0.9, "GFS": 0.3, "ICON": 0.6, "GEM": 0.6}
    snow = {"Euro": 9.0, "GFS": 3.0, "ICON": 6.0, "GEM": 6.0}
    assert B._disagreement(spread(liquid, snow))["basis"] == "liquid"


def test_needs_two_models():
    assert B._disagreement({"Euro": {"total_precip_in": 0.5, "total_snow_in": 0.0}}) is None
    assert B._disagreement({}) is None
    assert B._disagreement(None) is None


# --- what the writer is actually shown -------------------------------------------

def test_brief_labels_liquid_and_snow_on_a_rain_day():
    """No bare 'in' numbers, and never 'dry' beside a wet band forecast."""
    out = CO.render_bundle({"model_disagreement": B._disagreement(spread(SEP_25))})
    assert "all models dry" not in out
    assert "liquid precipitation" in out and "snowfall" in out
    assert "'Euro': 0.93" in out and "'GEM': 0.54" in out
    assert "judged on liquid" in out


def _rain_only_fetchers():
    """Same wiring as the end-to-end fixture, but rain in September."""
    f = fake_fetchers()
    mult = {"ecmwf_ifs025": 1.0, "gfs_seamless": 0.85,
            "icon_seamless": 0.78, "gem_seamless": 0.58}

    def rain_spread(band, days=5):
        out = {}
        for m, k in mult.items():
            p = json.loads(json.dumps(PAYLOAD))
            p["hourly"]["snowfall"] = [0.0 for _ in p["hourly"]["snowfall"]]
            p["hourly"]["precipitation"] = [x * k for x in p["hourly"]["precipitation"]]
            out[m] = SourceResult(True, p, source=m)
        return out

    f["spread"] = rain_spread
    return f


def test_build_on_a_rain_day_reports_rain_not_dry():
    """Through bundle.build(), so the summarizing step is covered too."""
    d = B.build(fetchers=_rain_only_fetchers())["model_disagreement"]
    assert d["level"] != "none -- all models dry"
    assert d["basis"] == "liquid"
    assert d["all_liquid"]["Euro"] > d["all_liquid"]["GEM"] > 0
    assert set(d["all_snow"].values()) == {0.0}
