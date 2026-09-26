"""The final round must spend the fixes it is holding, not discard them.

WHAT THIS IS FOR. Between 2026-09-19 and 2026-09-26 the forecaster composed a
draft every morning and the panel held all eight; nothing reached the website
for eight days. The 2026-09-26 transcript is the representative case: the
magistrate rejected a publishable post with

    "While all four issues are fixable with simple edits, the rules for this
     round require rejection of any draft that is not publishable as written."

and every one of those four issues arrived with an exact `->` replacement from
the editor. The fixtures below are that round, verbatim from
state/panel/2026-09-26-school_call.md.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from wx import review_panel as RP  # noqa: E402

# --- the 2026-09-26 round 3 draft, verbatim -------------------------------------
DRAFT_0926 = """09/26/26 5:45am: The dog wanted out early and the air's got that cool edge to it this morning.

Dry day across the board. Durango and the Animas Valley (6,500') should hit the low to mid 70s with clear skies through the afternoon. Bayfield and up the Pine (6,900') looking at the same, topping out in the low 70s. Vallecito and the Florida (7,650') will run a few degrees cooler, upper 60s, but still plenty of sun. The high Weminuche (10,500'+) stays in the mid 50s.

Zero precip in the forecast for today. The models all agree on that, which doesn't happen often enough to ignore when it does.

Snow line for Sunday evening sits around 11,350 feet, so the passes stay rain at pass level. Coal Bank, Molas and Red Mountain should stay dry through the weekend. Wolf Creek could see wet pavement Sunday evening. Current status is at cotrip.org, the forecast's mine and the road conditions are theirs.

Anybody planning to get on the water at the lake this weekend?"""

# --- the editor's round 3 report, verbatim --------------------------------------
EDITOR_0926 = {"verdict": "issues", "issues": [
    {"severity": "critical",
     "quote": "Coal Bank, Molas and Red Mountain should stay dry through the weekend.",
     "problem": "States a road condition for tomorrow without hedging.",
     "evidence": "LIVE ROAD STATUS: YOU HAVE NONE.",
     "fix": "Coal Bank, Molas and Red Mountain look like they'll stay dry through the weekend."},
    {"severity": "critical",
     "quote": "Wolf Creek could see wet pavement Sunday evening.",
     "problem": "States a Sunday road condition without the required phrasing.",
     "evidence": "LIVE ROAD STATUS: YOU HAVE NONE.",
     "fix": "Wolf Creek should see wet pavement Sunday evening."},
    {"severity": "major",
     "quote": "The dog wanted out early and the air's got that cool edge to it this morning.",
     "problem": "Two personal details when the rulebook requires exactly one.",
     "evidence": "PERSONA: Every post contains exactly one concrete detail.",
     "fix": "The dog wanted out early this morning."},
    {"severity": "major",
     "quote": "Anybody planning to get on the water at the lake this weekend?",
     "problem": "Closing question reuses the construction of 2026-09-20's closer.",
     "evidence": "2026-09-20 closed: What're you getting into today with the clear weather?",
     "fix": "How's the reservoir looking from your place this morning?"},
]}

# The round 3 fact checker flagged one sentence, then immediately retracted it
# about the very same sentence ("on second review ... this is actually
# supported"). Both verbatim, because the dedup rule exists for exactly this.
FACTS_0926 = {"verdict": "issues", "issues": [
    {"severity": "critical",
     "quote": "They're watching tropical moisture from a pair of hurricanes, Odalys and Polo, that could get pulled north into the Four Corners by Monday.",
     "problem": "The brief says Polo is a hurricane but Odalys is not specified as one.",
     "evidence": "drawing moisture from a pair of Hurricanes; Odalys and Polo.", "fix": ""},
    {"severity": "critical",
     "quote": "They're watching tropical moisture from a pair of hurricanes, Odalys and Polo, that could get pulled north into the Four Corners by Monday.",
     "problem": "On second review, the brief does say 'a pair of Hurricanes; Odalys and Polo', so this is actually supported.",
     "evidence": "drawing moisture from a pair of Hurricanes; Odalys and Polo.", "fix": ""},
]}

CLEAN = {"verdict": "clean", "issues": []}


def test_the_0926_rejection_now_approves_with_the_editors_own_replacements():
    """Acceptance check 2: replay 2026-09-26 through the patched final round."""
    patched, applied, skipped = RP._apply_fixes(
        DRAFT_0926, (("fact checker", FACTS_0926), ("editor", EDITOR_0926)))

    assert len(applied) == 4, [a["quote"] for a in applied]
    assert not skipped

    # The two road sentences the editor wanted hedged are hedged.
    assert "look like they'll stay dry through the weekend" in patched
    assert "Wolf Creek should see wet pavement Sunday evening." in patched
    # The opener is trimmed to a single personal detail.
    assert patched.startswith(
        "09/26/26 5:45am: The dog wanted out early this morning.")
    assert "cool edge" not in patched
    # The reused closer is replaced.
    assert patched.rstrip().endswith(
        "How's the reservoir looking from your place this morning?")

    # The self-retracting fact pair collapses to one, and it no longer quotes
    # any sentence in the patched text (that paragraph was not part of round 3's
    # draft here), so nothing from the fact checker stands in the way.
    assert RP._blocking_fact_issues(FACTS_0926, patched) == []


def test_a_fact_objection_with_no_replacement_still_holds_the_post():
    """Reject has to stay reachable. The fact checker is the only guard against
    a number the brief does not contain, and 5:45am is not recoverable."""
    text = "09/26/26 5:45am: Quiet morning.\n\nWe picked up 4 inches overnight.\n\nHow's yours?"
    facts = {"verdict": "issues", "issues": [
        {"severity": "critical", "quote": "We picked up 4 inches overnight.",
         "problem": "NOT IN BRIEF", "evidence": "NOT IN BRIEF", "fix": ""}]}
    patched, applied, _ = RP._apply_fixes(text, (("fact checker", facts),))
    assert applied == []
    assert RP._blocking_fact_issues(facts, patched), "an unsupported number must hold the post"


def test_a_superseded_quote_is_skipped_not_guessed_at():
    """Two reviewers on the same sentence: the second suggestion is skipped
    rather than applied to text that no longer contains its quote."""
    text = "09/26/26 5:45am: Quiet morning.\n\nThe passes are dry.\n\nHow's yours?"
    ed = {"verdict": "issues", "issues": [
        {"severity": "critical", "quote": "The passes are dry.",
         "problem": "present tense", "evidence": "PERSONA",
         "fix": "The passes should stay dry."}]}
    fc = {"verdict": "issues", "issues": [
        {"severity": "major", "quote": "The passes are dry.",
         "problem": "also present tense", "evidence": "PERSONA",
         "fix": "I'd expect the passes to stay dry."}]}
    patched, applied, skipped = RP._apply_fixes(text, (("editor", ed), ("fact checker", fc)))
    assert [a["fix"] for a in applied] == ["The passes should stay dry."]
    assert [s["who"] for s in skipped] == ["fact checker"]
    assert "I'd expect" not in patched


# --- Fix 3: the editor must not raise road tense at all -------------------------

ROAD_SENTENCES = ("Coal Bank, Molas and Red Mountain should stay dry through the weekend. "
                  "Wolf Creek could see wet pavement Sunday evening.")


def test_the_two_0926_road_sentences_pass_the_gate_that_owns_the_rule():
    """Acceptance check 3, deterministic half: the gate is the authority, and it
    passes both sentences. The editor called them [critical] anyway."""
    from wx import guardrails as G
    from test_guardrails import GOOD_BUNDLE, GOOD_DRAFT
    verdict, why = G.evaluate(GOOD_BUNDLE, GOOD_DRAFT + " " + ROAD_SENTENCES,
                              first_30_days=False)
    assert verdict != G.BLOCK, why
    assert not [r for r in why if "road" in r.lower() or "pass" in r.lower()], why


def test_editor_prompt_forbids_raising_road_tense():
    """Acceptance check 3, prompt half. The old prompt told the editor to check
    'Roads and passes only in future or conditional tense', which is the gate's
    rule; it then flagged two correctly hedged sentences as critical."""
    sys_prompt = RP.EDITOR_SYSTEM
    assert "Roads and passes only in future or conditional tense." not in sys_prompt
    assert "DO NOT raise a road or pass tense issue" in sys_prompt
    for hedge in ("should", "would", "could", "I'd expect", "looks like"):
        assert hedge in sys_prompt
    assert "CORRECT BY CONSTRUCTION" in sys_prompt


def test_editor_is_told_what_the_gate_already_passed(monkeypatch):
    """The gate verdict reaches the editor, so 'nothing flagged' is visible."""
    seen = {}

    def fake_llm(msgs):
        seen["user"] = msgs[-1]["content"]
        return '{"verdict":"clean","issues":[]}'

    monkeypatch.setattr(RP.CO, "load_system_prompt", lambda: "PERSONA")
    RP.edit_review(fake_llm, "draft text", {"recent_posts": []}, [],
                   brief="BRIEF", gate_verdict="pass", gate_reasons=[])
    assert "AUTOMATED RULE GATE, ALREADY RUN ON THIS DRAFT: PASS" in seen["user"]
    assert "Do not re-litigate" in seen["user"]


def test_0926_after_fix3_keeps_the_road_sentences_and_still_approves():
    """Acceptance check 2 as written: with the road false positives gone (Fix 3),
    only the two real issues are patched and the road sentences survive
    untouched, exactly as the writer composed them."""
    editor_after_fix3 = {"verdict": "issues", "issues": [
        i for i in EDITOR_0926["issues"] if "Coal Bank" not in i["quote"]
        and "Wolf Creek" not in i["quote"]]}
    assert len(editor_after_fix3["issues"]) == 2

    patched, applied, skipped = RP._apply_fixes(
        DRAFT_0926, (("fact checker", FACTS_0926), ("editor", editor_after_fix3)))

    assert len(applied) == 2 and not skipped
    # the two road sentences are byte-identical to the writer's text
    assert "Coal Bank, Molas and Red Mountain should stay dry through the weekend." in patched
    assert "Wolf Creek could see wet pavement Sunday evening." in patched
    # opener trimmed to one personal detail, closer replaced
    assert patched.startswith("09/26/26 5:45am: The dog wanted out early this morning.")
    assert patched.rstrip().endswith("How's the reservoir looking from your place this morning?")
    assert RP._blocking_fact_issues(FACTS_0926, patched) == []
