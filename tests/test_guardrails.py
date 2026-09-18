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
    assert any("above every peak" in r for r in why), why


def test_saying_it_is_all_rain_instead_passes():
    above = dict(GOOD_BUNDLE,
                 snow_line={"representative_ft": 14050, "above_terrain": True})
    v, why = G.evaluate(above, GOOD_DRAFT + " Its all rain today, right to the "
                                            "summits, no snow anywhere.",
                        calibrated=True)
    assert v == G.PASS, why
