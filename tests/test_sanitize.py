"""
Machine tells, removed.

The em dash is the most reliable giveaway there is. A model reaches for one
constantly, and a hyperlocal weather page that uses one in every post reads as
generated even when the substance is sound. The prompt asks for none; this
guarantees it, because a prompt rule is a request and a transform is a fact.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from wx import guardrails as G
from wx.sanitize import clean, has_tells, strip_dashes


def test_em_dash_becomes_a_comma():
    assert clean("The 240 is the one to watch — not this morning.") == \
        "The 240 is the one to watch, not this morning."


def test_paired_dashes_both_go():
    out = clean("Coal Bank and Molas — they close as a unit — get the most.")
    assert "—" not in out and out.count(",") == 2


def test_ranges_stay_hyphens_not_commas():
    """The voice is full of ranges. Turning 8-14 into '8, 14' would be worse
    than the dash it replaced."""
    assert clean("8–14 inches") == "8-14 inches"
    assert clean("Storms fire 2pm–5pm") == "Storms fire 2pm-5pm"
    assert clean("best chances 3–6pm") == "best chances 3-6pm"


def test_smart_quotes_and_ellipsis_go():
    out = clean("It’s not about the rain… it’s about where it’s falling")
    assert "'" in out and "’" not in out and "…" not in out


def test_idempotent():
    once = clean("Vallecito — 8–14 inches — overnight.")
    assert clean(once) == once


def test_no_doubled_punctuation():
    assert ",," not in clean("Up the Pine, — and the Florida — expect rain.")
    assert " ," not in clean("Dry this morning —, then storms.")


def test_has_tells_reports_survivors():
    assert has_tells("clean text") == []
    assert "em or en dash" in has_tells("something — here")[0]


def test_guardrail_blocks_a_dash_that_survived():
    bundle = {"missing": [], "bands": {"durango": {"ok": True}, "bayfield": {"ok": True},
                                       "vallecito": {"ok": True}},
              "life_safety_alerts": [], "snow_line": None}
    good = ("08/31/26 5:45am: Morning, its Monday. Dry through the morning up "
            "the Pine and the 501 looks fine. Storms build after noon, best "
            "chances 2pm-5pm. How is it looking out your window?")
    assert G.evaluate(bundle, good)[0] == G.PASS
    v, why = G.evaluate(bundle, good + " The 240 is the one to watch — later.")
    assert v == G.BLOCK and any("dash" in w for w in why)


def test_real_draft_shape_survives_cleaning():
    draft = ("08/31/26 5:45am: Morning, its Monday.\n\n"
             "The snow line is up at 13,100 feet — so this is all rain.\n\n"
             "Vallecito and the Florida (7,650'+) — models have about four "
             "hundredths at the lake, with 8–14 inches possible up high.\n\n"
             "Did your gauge catch anything overnight?")
    out = clean(draft)
    assert has_tells(out) == []
    assert "8-14 inches" in out
    assert "13,100 feet, so this is all rain" in out
    assert out.startswith("08/31/26 5:45am: Morning, its Monday.")
