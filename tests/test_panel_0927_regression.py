"""The final round must apply the ruling it was given, and check what it applied.

WHAT THIS IS FOR. On 2026-09-27 the magistrate required five changes. The
fifth, "Today's dry everywhere." -> "Today stays dry.", existed only in the
ruling, because the editor had flagged that sentence without supplying a fix;
_apply_fixes was fed only the reviewers' reports, so it vanished and the post
published with a sentence the magistrate had ruled must change. The log said
"skipped 0".

The same morning, the editor's own minor fix appended "and none of them have
been consistent run to run". The pipeline holds no prior-run data anywhere,
and nothing fact checked the patched text, so that reached the page
unverifiable.

The fixtures below are round 3 of state/panel/2026-09-27-school_call.md,
verbatim where it matters.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))

from test_runners import CLEAN_DRAFT, _fakes  # noqa: E402
from wx import bundle as B                     # noqa: E402
from wx import review_panel as RP              # noqa: E402

# --- 2026-09-27 round 3, the sentences that matter, verbatim -----------------
OPENER = ("Morning, its Sunday. The truck windows were dry and the sky's still "
          "clear, which wont last past tonight.")
PIVOT = "Today's dry everywhere."
GRAIN = "Dont put much faith in any single number, the spread's over an inch and a half."
DRAFT_0927 = (f"09/27/26 5:45am: {OPENER}\n\n{PIVOT} Durango and the Animas "
              f"Valley (6,500') should see sunny skies and mid-70s this "
              f"afternoon.\n\nThe models are all over the place on totals. "
              f"{GRAIN}\n\nDid you pull the boat already or is it still down "
              f"at the ramp?")

EDITOR_0927 = {"verdict": "issues", "issues": [
    {"severity": "major", "quote": OPENER,
     "problem": "Opener reuses a recent construction.", "evidence": "PERSONA",
     "fix": ("Morning, its Sunday. Truck windows were dry when I went out and "
             "the sky's still clear, but that changes overnight.")},
    # Flagged, and no fix. This is the one that got lost.
    {"severity": "major", "quote": PIVOT,
     "problem": "Repeats the pivot construction from 2026-09-14.",
     "evidence": "PERSONA", "fix": ""},
    {"severity": "minor", "quote": GRAIN,
     "problem": "Grain-of-salt phrasing needs the reason in parentheses.",
     "evidence": "PERSONA",
     "fix": ("Dont put much faith in any single number (the spread's over an "
             "inch and a half and none of them have been consistent run to run).")},
]}

RULING_0927 = {"ruling": "revise", "title": "", "dismissed": [],
               "rationale": "The editor correctly identified issues that must be fixed.",
               "required_changes": [
    f'"{OPENER}" -> "Morning, its Sunday. Truck windows were dry when I went out '
    'and the sky\'s still clear, but that changes overnight."',
    f'"{PIVOT}" -> "Today stays dry."',
    f'"{GRAIN}" -> "Dont put much faith in any single number (the spread\'s over '
    'an inch and a half and none of them have been consistent run to run)."',
]}

CLEAN = {"verdict": "clean", "issues": []}


def test_the_magistrate_only_change_is_extracted_and_applied():
    fixes, unapplied = RP._magistrate_fixes(RULING_0927, DRAFT_0927)
    assert unapplied == []
    assert {"severity": "major", "quote": PIVOT, "fix": "Today stays dry."} in fixes

    patched, applied, skipped, _ = RP._apply_fixes(
        DRAFT_0927, (("fact checker", CLEAN), ("editor", EDITOR_0927),
                     ("magistrate", {"issues": fixes, "overrides": True})))
    assert "Today stays dry." in patched
    assert PIVOT not in patched, "the ruling said this sentence must change"
    # Two editor fixes, and the pivot from the ruling. The ruling's copies of
    # the editor's two fixes are the same words, so neither applied twice nor
    # reported as skipped: "skipped 0" has to mean nothing was skipped.
    assert [a["who"] for a in applied] == ["editor", "editor", "magistrate"]
    assert skipped == []


def test_an_instruction_is_never_spliced_into_the_post():
    """Half of required_changes are instructions. "write a fresh closer" got
    past an early word-list-only version because "write" was not listed, and it
    would have become the post's closing line."""
    closer = "Did you pull the boat already or is it still down at the ramp?"
    for instruction in ("write a fresh closer",
                        "Rewrite this as a forecast, not a statement.",
                        "cut to one concrete detail",
                        "Replace with something that is not a question",
                        "(drop the second clause)",
                        "use a different closing question"):
        ruling = {"required_changes": [f'"{closer}" -> {instruction}']}
        fixes, unapplied = RP._magistrate_fixes(ruling, DRAFT_0927)
        assert fixes == [], instruction
        assert [u["quote"] for u in unapplied] == [closer], instruction
    assert not RP._looks_like_prose(closer, "write a fresh closer")
    assert RP._looks_like_prose(closer, "Anybody still got a dock in the water?")


def test_a_note_about_the_writing_is_never_spliced_in_even_when_shaped_like_prose():
    """Capital first letter, terminal period, no blacklisted opening verb, and
    still not a sentence that belongs in a forecast."""
    for note in ("Needs a hedge.", "Too close to the 09-14 opener.",
                 "This sentence repeats a retired pivot.",
                 "The wording here is too certain."):
        fixes, unapplied = RP._magistrate_fixes(
            {"required_changes": [f'"{PIVOT}" -> "{note}"']}, DRAFT_0927)
        assert fixes == [], note
        assert [u["quote"] for u in unapplied] == [PIVOT], note
    fixes, _ = RP._magistrate_fixes(
        {"required_changes": [f'"{PIVOT}" -> "Today stays dry."']}, DRAFT_0927)
    assert [f["fix"] for f in fixes] == ["Today stays dry."]


def test_a_fix_may_not_smuggle_a_dash_back_in():
    ruling = {"required_changes": [
        f'"{PIVOT}" -> "Today stays dry -- for now."',
        f'"{PIVOT}" -> "Today stays dry — for now."']}
    fixes, unapplied = RP._magistrate_fixes(ruling, DRAFT_0927)
    assert fixes == []
    assert all("dash" in u["why"] for u in unapplied) and len(unapplied) == 2


def test_the_ruling_wins_over_a_different_reviewer_fix():
    """Applied last so the ruling wins, not merely so it runs last. And a plain
    list is accepted as a report."""
    editor = [{"quote": PIVOT, "fix": "Today's dry all over.", "severity": "major"}]
    mag = {"issues": [{"quote": PIVOT, "fix": "Today stays dry."}], "overrides": True}
    patched, applied, skipped, _ = RP._apply_fixes(
        DRAFT_0927, (("editor", editor), ("magistrate", mag)))
    assert "Today stays dry." in patched
    assert "Today's dry all over." not in patched
    assert [a["who"] for a in applied] == ["editor", "magistrate"] and not skipped


# --- through the loop, with scripted roles ------------------------------------

class Script:
    """Routes by system prompt. facts is a list consumed one call at a time
    (the last entry repeats), so a re-check can answer differently."""

    def __init__(self, ruling, facts=None, editor=None):
        self.ruling = ruling
        self.facts = list(facts or [CLEAN])
        self.editor = editor or CLEAN
        self.calls = []

    def __call__(self, messages):
        system = next(m["content"] for m in messages if m["role"] == "system")
        if system.startswith("You are the fact checker"):
            out = self.facts.pop(0) if len(self.facts) > 1 else self.facts[0]
            self.calls.append(("facts", messages))
        elif system.startswith("You are the editor"):
            out = self.editor
            self.calls.append(("editor", messages))
        elif system.startswith("You are the magistrate"):
            out = self.ruling
            self.calls.append(("magistrate", messages))
        else:
            self.calls.append(("writer", messages))
            return CLEAN_DRAFT
        return out if isinstance(out, str) else json.dumps(out)

    def facts_calls(self):
        return [m for role, m in self.calls if role == "facts"]


CLOSER = "How is it looking out your window?"
NEW_CLOSER = "Anybody up the Florida already chaining up?"
DETAIL = ("At the house the woodpile is still buried and the dog wanted no "
          "part of the yard.")


def _panel(script):
    return RP.run_panel(B.build(fetchers=_fakes()), CLEAN_DRAFT, slot="school_call",
                        writer_llm=script, rounds=1, log=lambda *_: None)


def _revise(*changes):
    return {"ruling": "revise", "required_changes": list(changes), "dismissed": [],
            "title": "", "rationale": "Fix these."}


def test_an_outstanding_change_surfaces_and_blocks_approval():
    s = Script(_revise(f'"{CLOSER}" -> "{NEW_CLOSER}"',
                       f'"{DETAIL}" -> cut this to one concrete detail'))
    out = _panel(s)
    assert out["approved"] is False, "four of five applied is not the ruling"
    ap = out["rounds"][-1]["autopatch"]
    assert [o["quote"] for o in ap["outstanding"]] == [DETAIL]
    assert [a["fix"] for a in ap["applied"]] == [NEW_CLOSER]
    t = RP.transcript(out, B.build(fetchers=_fakes()), "school_call")
    assert "NOT applied" in t and DETAIL in t


def test_a_change_whose_sentence_is_already_gone_is_not_outstanding():
    editor = {"verdict": "issues", "issues": [
        {"severity": "major", "quote": DETAIL, "problem": "two details",
         "evidence": "PERSONA", "fix": "At the house the dog wanted no part of the yard."}]}
    s = Script(_revise(f'"{DETAIL}" -> trim to one detail'), editor=editor)
    out = _panel(s)
    ap = out["rounds"][-1]["autopatch"]
    assert ap["outstanding"] == []
    assert out["approved"] is True, out["reason"]


def test_the_patched_text_is_fact_checked_again_and_sees_the_patch():
    s = Script(_revise(f'"{CLOSER}" -> "{NEW_CLOSER}"'))
    out = _panel(s)
    assert out["approved"] is True, out["reason"]
    calls = s.facts_calls()
    assert len(calls) == 2
    second = calls[1][-1]["content"]
    assert NEW_CLOSER in second and CLOSER not in second


def test_an_unsupported_claim_from_a_fix_holds_the_post():
    """The 09-27 shape: a reviewer's own fix says something nothing holds, and
    the first fact check never saw that sentence."""
    claim = ("None of the models have been consistent run to run, so how is "
             "it looking out your window?")
    editor = {"verdict": "issues", "issues": [
        {"severity": "minor", "quote": CLOSER, "problem": "flat closer",
         "evidence": "PERSONA", "fix": claim}]}
    bad = {"verdict": "issues", "issues": [
        {"severity": "critical", "quote": claim, "problem": "no prior-run data",
         "evidence": "NOT IN BRIEF", "fix": ""}]}
    s = Script(_revise(), facts=[CLEAN, bad], editor=editor)
    out = _panel(s)
    assert out["approved"] is False
    assert claim in out["rounds"][-1]["autopatch"]["blocking_facts"]


def test_an_unreadable_recheck_holds_the_post():
    s = Script(_revise(f'"{CLOSER}" -> "{NEW_CLOSER}"'),
               facts=[CLEAN, "looks fine to me!"])
    out = _panel(s)
    assert out["approved"] is False, "a missing review is not a clean review"
    assert "could not be read" in out["rounds"][-1]["autopatch"]["recheck_problem"]


def test_no_patch_means_no_extra_model_call():
    s = Script(_revise())
    out = _panel(s)
    assert out["approved"] is False
    assert len(s.facts_calls()) == 1
