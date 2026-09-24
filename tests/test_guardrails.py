import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from wx import guardrails as G

GOOD_BUNDLE = {
    "missing": [],
    "bands": {"durango": {"ok": True}, "bayfield": {"ok": True},
              "vallecito": {"ok": True}, "weminuche": {"ok": True}},
    "life_safety_alerts": [],
    "snow_line": {"representative_ft": 7200},
}
GOOD_DRAFT = ("11/04/26 5:52am: Morning. Snow line about 7,200ft this morning, "
              "take that with a grain of salt (its been running low all night). "
              "Durango is just wet. Up the Pine 2-5 inches. How's it look out "
              "your window?")


def test_clean_draft_passes():
    v, why = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT)
    assert v == G.PASS, why


def test_missing_band_blocks():
    b = {**GOOD_BUNDLE, "bands": {**GOOD_BUNDLE["bands"], "vallecito": {"ok": False}}}
    v, why = G.evaluate(b, GOOD_DRAFT)
    assert v == G.BLOCK and any("vallecito" in w for w in why)


def test_missing_alerts_blocks():
    v, _ = G.evaluate({**GOOD_BUNDLE, "missing": ["alerts"]}, GOOD_DRAFT)
    assert v == G.BLOCK


def test_life_safety_alert_forces_review():
    b = {**GOOD_BUNDLE, "life_safety_alerts": [{"event": "Winter Storm Warning"}]}
    v, why = G.evaluate(b, GOOD_DRAFT)
    assert v == G.REVIEW and any("Winter Storm Warning" in w for w in why)


def test_burn_scar_forces_review():
    v, why = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " Watch the 416 scar this afternoon.")
    assert v == G.REVIEW and any("burn scar" in w for w in why)


def test_credential_claim_blocks():
    v, _ = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " As a certified meteorologist I can tell you.")
    assert v == G.BLOCK


def test_school_closure_announcement_blocks():
    v, _ = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " Schools are closed today.")
    assert v == G.BLOCK


def test_politics_blocks():
    v, _ = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " The president said otherwise.")
    assert v == G.BLOCK


def test_lake_effect_blocks():
    v, _ = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " Some lake-effect snow off Vallecito tonight.")
    assert v == G.BLOCK


def test_florida_mispronunciation_blocks():
    v, _ = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " Out on the FLOR-ida Road it is icy.")
    assert v == G.BLOCK


def test_uncalibrated_snow_line_without_hedge_reviews():
    bare = ("11/04/26 5:52am: Morning. Snow line is 7,200ft. Durango is wet, "
            "up the Pine 2-5 inches on the ground by daybreak. How's it look?")
    v, why = G.evaluate(GOOD_BUNDLE, bare, calibrated=False)
    assert v == G.REVIEW and any("hedge" in w for w in why)


def test_calibrated_snow_line_needs_no_hedge():
    bare = ("11/04/26 5:52am: Morning. Snow line is 7,200ft. Durango is wet, "
            "up the Pine 2-5 inches on the ground by daybreak. How's it look?")
    v, _ = G.evaluate(GOOD_BUNDLE, bare, calibrated=True)
    assert v == G.PASS


def test_snow_amount_far_out_reviews():
    v, why = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " Looks like 10-14 inches five days out.")
    assert v == G.REVIEW and any("beyond day 3" in w for w in why)


def test_first_30_days_reviews_everything():
    v, _ = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT, first_30_days=True)
    assert v == G.REVIEW


def test_short_draft_blocks():
    v, _ = G.evaluate(GOOD_BUNDLE, "too short")
    assert v == G.BLOCK


def test_credential_claims_in_several_forms_all_block():
    for claim in [
        "As a certified meteorologist I can tell you.",
        "I am a meteorologist and I think this verifies.",
        "I'm a meteorologist, so trust me on this one.",
        "My degree in atmospheric science says otherwise.",
        "I studied this exact setup in school.",
        "Speaking as a career meteorologist here.",
    ]:
        v, why = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " " + claim)
        assert v == G.BLOCK, f"should have blocked: {claim!r} -> {why}"


def test_ordinary_expertise_language_still_passes():
    # The persona IS allowed to sound like it knows what it is doing. It just
    # cannot claim a credential it does not hold.
    for ok in [
        "I've watched this setup a dozen times up here.",
        "I look at these models every morning.",
        "In my experience the 240 ices before anything else does.",
    ]:
        v, why = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " " + ok)
        assert v == G.PASS, f"should have passed: {ok!r} -> {why}"


def test_the_ordinary_word_florida_is_allowed():
    # Regression guard. The persona says "the Florida Road" and "the Florida
    # drainage" constantly; blocking those would gut the local vocabulary that
    # is the entire moat.
    for ok in [
        "Vallecito and the Florida picked up a few inches.",
        "The Florida Road is the slick one this morning.",
        "Best of it lands over the Florida drainage.",
        "Lemon and the upper Florida did well.",
    ]:
        v, why = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " " + ok)
        assert v == G.PASS, f"should have passed: {ok!r} -> {why}"


def test_first_syllable_stress_gloss_still_blocks():
    for bad in [
        "Out on the FLOR-ida Road it is icy.",
        "The Flor-ih-duh Road is closed.",
        "locals say FLOR ida",
    ]:
        v, _ = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " " + bad)
        assert v == G.BLOCK, f"should have blocked: {bad!r}"


# --- the gauge and the stake -----------------------------------------------
#
# 2026-09-17 shipped "the snow stake here is still sitting at 5 inches" on an
# all-rain day with the snow line at 14,000 ft. state/home_gauge.json is {} and
# always has been, so no reading existed anywhere; the persona asks for exactly
# one personal detail and rotates which one, and the model filled the hole when
# the stake's turn came round.

def test_a_stake_or_gauge_reading_with_nothing_behind_it_is_blocked():
    for bad in [
        'The snow stake here is still sitting at 5" this morning.',
        "At the house I have got about three inches on the stake.",
        "The gauge showed 0.42 overnight.",
        "Gauge here caught 0.3 out of that band.",
        "Half an inch in the rain gauge at the house.",
    ]:
        v, why = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " " + bad)
        assert v == G.BLOCK, f"should have blocked: {bad!r} -> {why}"
        assert any("gauge or stake" in r for r in why), why
        # and it must be the kind of BLOCK the one-shot rewrite can fix
        assert G.text_fixable(why), why


def test_a_real_reading_is_allowed_and_a_wrong_one_is_not():
    bundle = dict(GOOD_BUNDLE, home_gauge={"precip_in": 0.42,
                                           "for_date": "2026-11-04"})
    v, why = G.evaluate(bundle, GOOD_DRAFT + " The gauge caught 0.42 overnight.")
    assert v == G.PASS, why
    v, why = G.evaluate(bundle, GOOD_DRAFT + " The gauge caught 0.85 overnight.")
    assert v == G.BLOCK, "a figure the reading does not contain is still invented"


def test_the_gauge_can_still_be_mentioned_without_a_number():
    # The voice needs this and it invents nothing. Only a FIGURE is the problem.
    for ok in [
        "The gauge here is dry and the sky is clear.",
        "Nothing in the gauge this morning.",
        "The stake is bare.",
        "Vallecito and the Florida picked up a few inches overnight.",
        "The 501 could see a couple inches by the 6:30 call.",
    ]:
        v, why = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " " + ok)
        assert v == G.PASS, f"should have passed: {ok!r} -> {why}"


def test_a_snow_line_figure_above_the_terrain_is_held_for_review():
    above = dict(GOOD_BUNDLE,
                 snow_line={"representative_ft": 14050, "above_terrain": True})
    v, why = G.evaluate(above, GOOD_DRAFT + " Snow line is up around 14,050 ft "
                                            "today so its all rain.",
                        calibrated=True)
    assert v == G.REVIEW, why
    assert any("above the passes" in r for r in why), why


def test_saying_it_is_all_rain_instead_passes():
    above = dict(GOOD_BUNDLE,
                 snow_line={"representative_ft": 14050, "above_terrain": True})
    v, why = G.evaluate(above, GOOD_DRAFT + " Its all rain today, right to the "
                                            "summits, no snow anywhere.",
                        calibrated=True)
    assert v == G.PASS, why


def test_the_preposition_in_is_not_an_inch_abbreviation():
    """Found by probing, not by a failure: every one of these was a BLOCK.

    This persona writes in exactly the register that trips a bare "in" as a
    unit, and the cost of the false positive is a blocked morning.
    """
    for ok in [
        "The gauge has been dry since 5 in the evening.",
        "Nothing in the gauge, and I was up at 4 in the morning.",
        "The stake is bare, got up at 6 in the dark to look.",
        "The gauge is empty, though theres 8 in the Weminuche tonight.",
    ]:
        v, why = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " " + ok)
        assert v == G.PASS, f"should have passed: {ok!r} -> {why}"


# --- road status: the 2026-09-21..24 review issues -------------------------
#
# Four of the five drafts to 2026-09-24 failed draft-lint's `road-status` rule
# and none of them tripped this module, because every pattern in
# ROAD_STATUS_CLAIMS is anchored on a verb. A claim with the verb left out
# ("Dry roads for the bus run") was invisible here, so correction_note() never
# fired and the model was never asked to rewrite it.

ROAD_CLAIMS = [
    # The four drafts, verbatim.
    "Dry roads for the bus run this morning.",
    "Bayfield and up the Pine same story, dry pavement and clear conditions "
    "through the morning.",
    "The 501, the 240, the 160 into town all look fine for the morning drive.",
    "The passes are getting wet pavement at most, maybe a couple inches way up "
    "high on Red Mountain or Wolf Creek but nothing at pass level.",
    # Every form system.md lists as forbidden, by name.
    "The 160 into town looks fine.",
    "Roads wet, no ice.",
    "The passes are dry.",
    "The 501 and the 240 are both dry for the school run.",
    # A hedge in one clause must not launder the claim in the other.
    "Coal Bank should stay dry, and Molas is clear right now.",
]

ROAD_FORECASTS = [
    # system.md's own prescribed repairs. These are the whole point of the
    # product and a false positive here is a silent morning.
    "The 160 should be fine for the morning commute.",
    "I'd expect dry pavement by the 6:30 call.",
    "Coal Bank should stay rain at pass level.",
    "Looks like it'll be wet pavement for the drive in.",
    "The 501 should be fine this morning but I'd plan for wet roads and maybe "
    "some ponding by the afternoon commute home.",
    "Not much, maybe a few hundredths, but enough to wet pavement for the "
    "evening commute.",
    "The 550 passes should turn wet through the afternoon, mostly rain at pass "
    "level even up at Red Mountain.",
    "That is the forecast, not the road status. Current closures and chain "
    "law: https://www.cotrip.org/",
]

# Weather and water sentences with a number in them that is not a route.
ROAD_NON_CLAIMS = [
    "Durango and the Animas Valley (6,500') stay dry today with highs in the "
    "mid-80s.",
    "The Florida is running 160 cfs and the lake is clear this morning.",
    "Vallecito sits at 7,650 ft.",
]


def test_present_tense_road_claims_block():
    for claim in ROAD_CLAIMS:
        assert G.road_status_claim(claim)[0], f"missed: {claim!r}"
        v, why = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " " + claim)
        assert v == G.BLOCK, f"expected BLOCK for {claim!r}: {why}"
        assert any("road surface" in w for w in why), why


def test_forecasting_the_roads_still_passes():
    """The gate must not block the thing the product exists to do."""
    for ok in ROAD_FORECASTS + ROAD_NON_CLAIMS:
        assert G.road_status_claim(ok)[0] is None, f"false positive: {ok!r}"
        v, why = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " " + ok)
        assert v == G.PASS, f"should have passed: {ok!r} -> {why}"


def test_a_number_that_is_not_a_route_is_not_a_road():
    """An elevation and a flow reading are not highways.

    `\\b501\\b` matches inside "(6,500')" -- the comma is a word boundary -- and
    `\\b160\\b` matches "running 160 cfs". Both read as road-status claims and
    both would have blocked a morning over a sentence with no road in it. The
    route number stays bare so "550 is closed" is still caught; the two numeric
    contexts are excluded instead. Asserted on the flat patterns as well as the
    detector, because the bug was in the flat patterns first.
    """
    import re
    for ok in ROAD_NON_CLAIMS:
        assert G.road_status_claim(ok)[0] is None, f"false positive: {ok!r}"
        for pattern, why in G.ROAD_STATUS_CLAIMS:
            assert not re.search(pattern, ok, re.IGNORECASE), f"{why}: {ok!r}"


def test_a_bare_route_number_is_still_a_road():
    """The exclusion must not cost the unadorned forms."""
    for claim in ["550 is closed.", "US-550 is closed.", "CR 501 is slick.",
                  "160 is icy over the top.", "The 501 is fine."]:
        assert G.road_status_claim(claim)[0], f"missed: {claim!r}"


def test_the_flat_patterns_are_hedge_aware_too():
    """ROAD_STATUS_CLAIMS used to be matched flat against the whole draft.

    That made it the only road rule in the project with no notion of tense. It
    blocked a conditional, and it blocked the phrasing constants.py holds up as
    the honest product: "Coal Bank and Molas, 8-14 inches overnight, expect
    traction law by morning".
    """
    for forecast in [
        "If that band sets up, the 550 is icy by 6am and Molas is slick.",
        "Expect chain law up on Red Mountain by morning.",
        "Coal Bank and Molas, 8-14 inches overnight, expect traction law by "
        "morning.",
    ]:
        assert G.road_status_claim(forecast)[0] is None, f"blocked: {forecast!r}"
        v, why = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " " + forecast)
        assert v == G.PASS, f"should have passed: {forecast!r} -> {why}"


def test_a_closure_cannot_be_hedged():
    """The one road rule that ignores the hedges and the conditional opener.

    A surface forecast is a weather claim and hedging is what makes it honest.
    Whether a gate is down is not weather: it is CDOT's decision, there is no
    feed for it, and "Wolf Creek will likely be closed" is not a hedged version
    of a fact we hold. At 5:45am it reads like "Wolf Creek is closed" and sends
    the same person on the same three-hour detour.
    """
    for claim in [
        "Wolf Creek will likely be closed if this verifies.",
        "Red Mountain should be closed by noon.",
        "I'd expect the 550 to be shut through the morning.",
        "If you are heading north, Red Mountain is closed.",
        "The 550 closes at six.",
        "Molas reopens later today.",
        "Expect Wolf Creek to stay open all day.",
        "CDOT has closed Molas.",
    ]:
        stated, why = G.road_status_claim(claim)
        assert stated, f"missed: {claim!r}"
        v, reasons = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " " + claim)
        assert v == G.BLOCK, f"expected BLOCK for {claim!r}: {reasons}"


def test_chain_law_stays_hedgeable_though():
    """constants.py holds "expect traction law by morning" up as the product.

    A traction law is a consequence of the weather we do have, unlike a gate
    coming down, so it is forecastable and tests/test_passes.py pins that.
    """
    for ok in ["Expect traction law by morning over Wolf Creek.",
               "Expect chain law up on Red Mountain by morning."]:
        assert G.road_status_claim(ok)[0] is None, f"blocked: {ok!r}"
    for claim in ["Chain law is on over Wolf Creek.",
                  "Traction law is in effect on the 550."]:
        assert G.road_status_claim(claim)[0], f"missed: {claim!r}"


def test_a_time_window_alone_does_not_hedge_a_present_tense_claim():
    """The hole that hedge-awareness would otherwise have opened.

    "through the morning" says when, not whether. "The passes are dry through
    the morning" still asserts that they are dry right now, and the flat
    patterns have always blocked it; running them through an undifferentiated
    hedge list would have let it through. Only the modal tier hedges.
    """
    for claim in ["The passes are dry through the morning.",
                  "The 501 is clear all day.",
                  "Roads are wet tonight."]:
        assert G.road_status_claim(claim)[0], f"missed: {claim!r}"
    for ok in ["The passes should be dry through the morning.",
               "The 501 should be clear all day."]:
        assert G.road_status_claim(ok)[0] is None, f"false positive: {ok!r}"


def test_live_cdot_data_makes_a_road_claim_legal():
    """With CDOT in the bundle a flat present-tense statement is just data."""
    live = {**GOOD_BUNDLE, "roads": {"us550": {"status": "closed"}}}
    v, why = G.evaluate(live, GOOD_DRAFT + " Red Mountain is closed.")
    assert v == G.PASS, why


def test_a_blocked_road_claim_is_rewritable_rather_than_fatal():
    """It is a writing problem, so the run should rewrite, not go silent."""
    _, why = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " Dry roads for the bus run.")
    assert G.text_fixable(why), why
    note = G.correction_note(why)
    assert "dry roads" in note.lower(), note
    assert "adjective" in note.lower(), note
