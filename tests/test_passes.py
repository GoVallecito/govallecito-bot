"""
Pass forecasting, and the rule that we never report road status.

CDOT's public feed documentation has been withdrawn, so nothing behind this
product knows whether a road is open. A wrong "closed" sends someone on a
three-hour detour; a wrong "open" sends them at a pass that is shut. The rule
therefore lives in the guardrails, not only in the prompt, so a persuasive
draft cannot talk its way past it.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
from wx import constants as C, guardrails as G, passes as P
from wx.sources.http import SourceResult
from test_storm_watch import payload


def fake_band(snow_scale=1.0, gust=15):
    def _f(band, days=2, models=None):
        p = payload(hours=48, storm_at=6, intensity=0.10 * snow_scale)
        p["elevation"] = band["elevation_m"]
        n = len(p["hourly"]["time"])
        p["hourly"]["temperature_2m"] = [20.0] * n
        p["hourly"]["dew_point_2m"] = [18.0] * n
        p["hourly"]["freezing_level_height"] = [1500] * n
        p["hourly"]["wind_gusts_10m"] = [gust] * n
        p["hourly"]["precipitation_probability"] = [80] * n
        return SourceResult(True, p, source="stub")
    return _f


def test_all_four_passes_forecast():
    r = P.fetch(fetch_band=fake_band())
    assert r.ok
    assert set(r.data) == {"coal_bank", "molas", "red_mountain", "wolf_creek"}


def test_signed_elevations_are_used_in_copy():
    r = P.fetch(fetch_band=fake_band())
    card = P.format_card(r.data)
    assert "11,018 ft" in card, "Red Mountain's signed elevation"
    assert "10,857 ft" in card, "Wolf Creek's signed elevation"


def test_the_550_passes_are_described_as_a_unit():
    card = P.format_card(P.fetch(fetch_band=fake_band()).data)
    assert "close as a unit" in card
    assert "Coal Bank, Molas and Red Mountain" in card


def test_card_always_defers_to_cdot_for_status():
    card = P.format_card(P.fetch(fetch_band=fake_band()).data)
    assert "not the road status" in card
    assert C.CDOT_STATUS_URL in card


def test_card_never_claims_open_or_closed():
    card = P.format_card(P.fetch(fetch_band=fake_band(snow_scale=4)).data)
    low = card.lower()
    assert " is closed" not in low and " is open" not in low


def test_notable_snow_is_flagged_for_the_lead():
    assert P.worth_leading_with(P.fetch(fetch_band=fake_band(snow_scale=5)).data)
    assert not P.worth_leading_with(P.fetch(fetch_band=fake_band(snow_scale=0.01)).data)


# --- the guardrail ---------------------------------------------------------

BUNDLE = {"missing": [], "bands": {"durango": {"ok": True}, "bayfield": {"ok": True},
                                   "vallecito": {"ok": True}},
          "life_safety_alerts": [], "snow_line": None}
BASE = ("11/04/26 5:52am: Morning, its Wednesday. Cold and clear down in the "
        "Valley this morning and the stake at the house has an inch on it. "
        "How is it looking out your window up the Pine?")


def test_claiming_a_closure_without_data_is_blocked():
    for claim in [
        "Red Mountain Pass is closed this morning.",
        "The pass is closed, go around.",
        "US-550 is open again.",
        "Chain law is on over Wolf Creek.",
        "Traction law is in effect on the 550.",
        "CDOT has closed Molas.",
        "They're doing control work on Red Mountain.",
    ]:
        v, why = G.evaluate(BUNDLE, BASE + " " + claim)
        assert v == G.BLOCK, f"should have blocked: {claim!r} -> {why}"


def test_forecast_phrasing_about_the_passes_is_allowed():
    for ok in [
        "Coal Bank and Molas should pick up 8-14 inches overnight.",
        "Expect traction law by morning over Wolf Creek.",
        "If you are running the 550 today, check CDOT before you go.",
        "Wolf Creek is getting the best of this one.",
    ]:
        v, why = G.evaluate(BUNDLE, BASE + " " + ok)
        assert v == G.PASS, f"should have passed: {ok!r} -> {why}"


def test_status_claims_are_allowed_once_live_data_exists():
    with_roads = dict(BUNDLE, roads={"us550_north": {"summary": "closed"}})
    v, _ = G.evaluate(with_roads, BASE + " Red Mountain Pass is closed this morning.")
    assert v == G.PASS
