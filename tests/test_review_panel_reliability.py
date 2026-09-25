"""
Review-panel reliability, from the two 2026-09-25 smoke tests.

Three failures, each pinned here:
  1. The magistrate's round-1 reply was unreadable on both runs and nothing was
     kept, so the cause was a guess.
  2. The reviewers contradicted each other (exact figures vs ranges), the editor
     never saw the brief, and the fact checker called the harness's own stamp
     fabricated.
  3. A gauge reading nobody entered ("The gauge caught 0.08 overnight") came
     from the editor's suggested fix, and the reviser used it.
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))

import pytest

from test_review_panel import Script, ok, revise, _bundle, CLEAN_DRAFT
from wx import compose as CO
from wx import review_panel as RP
from wx import run_forecast as RF

QUIET = dict(log=lambda *_: None)


# --- 1. reading what the model actually sends ---------------------------------

@pytest.mark.parametrize("raw", [
    '{"ruling": "revise", "required_changes": ["a -> b"]}',
    '```json\n{"ruling": "revise", "required_changes": ["a -> b"]}\n```',
    'Here is my ruling:\n{"ruling": "revise", "required_changes": ["a -> b"]}\nThanks.',
    # Trailing comma.
    '{"ruling": "revise", "required_changes": ["a -> b",],}',
    # Unescaped inch marks inside a string: the usual way a weather reply breaks.
    '{"ruling": "revise", "required_changes": ["a -> b"], '
    '"rationale": "Bayfield says 0.05" through mid-morning and 0.93", GFS 0.79"."}',
])
def test_replies_models_actually_send_are_read(raw):
    obj = RP._parse_json(raw)
    assert obj and obj["ruling"] == "revise"


def test_a_reply_cut_off_by_max_tokens_is_repaired_and_marked():
    raw = ('{"ruling": "revise", "required_changes": ["quote one -> fix one", '
           '"quote two -> fix tw')
    obj = RP._parse_json(raw)
    assert obj["ruling"] == "revise"
    assert obj["required_changes"][0] == "quote one -> fix one"
    assert obj.get("_truncated") is True


def test_stray_quotes_are_kept_as_text_not_dropped():
    obj = RP._parse_json('{"a": "0.05" through mid-morning", "b": "x"}')
    assert obj == {"a": '0.05" through mid-morning', "b": "x"}


@pytest.mark.parametrize("raw", ["", "no json here", "{", "[1, 2, 3]"])
def test_garbage_is_none(raw):
    assert RP._parse_json(raw) is None


def test_truncated_magistrate_reply_still_drives_the_revision():
    cut = ('{"ruling": "revise", "required_changes": ["closer -> a new closer", '
           '"pivot -> a')
    s = Script([cut, ok()])
    out = RP.run_panel(_bundle(), CLEAN_DRAFT, slot="school_call", writer_llm=s,
                       rounds=2, **QUIET)
    first = out["rounds"][0]["ruling"]
    assert first["ruling"] == "revise" and not first.get("unparseable")
    assert first["required_changes"][0] == "closer -> a new closer"
    assert out["approved"] is True


def test_an_approval_from_a_cut_off_reply_does_not_count():
    """An approval publishes unattended; half a reply is not a signature."""
    cut = '{"ruling": "approve", "required_changes": [], "dismissed": [], "title": "Snow on the Fl'
    s = Script([cut])
    out = RP.run_panel(_bundle(), CLEAN_DRAFT, slot="school_call", writer_llm=s,
                       rounds=1, **QUIET)
    assert out["approved"] is False
    assert "cut off" in out["rounds"][0]["ruling"]["rationale"]


def test_an_approval_with_stray_inch_marks_does_count():
    """Only truncation voids an approval; a stray quote in the rationale is the
    model's typing, not a missing signature."""
    raw = ('{"ruling": "approve", "required_changes": [], "dismissed": [], '
           '"title": "Wet Friday morning", "rationale": "0.05" is in the brief."}')
    out = RP.run_panel(_bundle(), CLEAN_DRAFT, slot="school_call",
                       writer_llm=Script([raw]), rounds=1, **QUIET)
    assert out["approved"] is True
    assert out["title"] == "Wet Friday morning"


def test_the_retry_shows_the_model_its_own_bad_reply():
    bad = "Sure! I rule that we should revise, because reasons."
    s = Script([bad, ok()])
    RP.run_panel(_bundle(), CLEAN_DRAFT, slot="school_call", writer_llm=s,
                 rounds=1, **QUIET)
    mags = [c[1] for c in s.calls if c[0] == "magistrate"]
    assert len(mags) == 2, "one retry"
    retry = mags[1]
    assert retry[-2] == {"role": "assistant", "content": bad}
    assert "not valid JSON" in retry[-1]["content"]


def test_an_unreadable_ruling_keeps_the_raw_reply_and_salvages_revise():
    junk = 'My answer is "ruling": "revise" but <<< broken beyond repair >>>'
    s = Script([junk])
    out = RP.run_panel(_bundle(), CLEAN_DRAFT, slot="school_call", writer_llm=s,
                       rounds=1, **QUIET)
    ru = out["rounds"][0]["ruling"]
    assert ru["unparseable"] is True
    assert ru["ruling"] == "revise" and "recovered" in ru["rationale"]
    assert "broken beyond repair" in ru["raw_reply"]
    md = RP.transcript(out, _bundle(), "school_call")
    assert "could not be read" in md and "broken beyond repair" in md


def test_a_reviewer_cut_off_before_its_issues_is_not_clean():
    """Repairing '{"verdict": "issues", "issues": [' gives an empty list, which
    would read as a clean bill of health from a reviewer that ran out of room."""
    cut = '{"verdict": "issues", "issues": ['
    s = Script([ok()], facts=cut)
    out = RP.run_panel(_bundle(), CLEAN_DRAFT, slot="school_call", writer_llm=s,
                       rounds=1, **QUIET)
    assert out["rounds"][0]["fact_check"].get("unparseable") is True
    assert out["approved"] is False, "the missing review withholds approval"


def test_a_reviewer_cut_off_after_some_issues_keeps_them():
    cut = ('{"verdict": "issues", "issues": [{"severity": "critical", "quote": "q", '
           '"problem": "p", "evidence": "NOT IN BRIEF", "fix": ""}, {"severity": "maj')
    s = Script([ok()], facts=cut)
    rep = RP.fact_check(s, BRIEF, CLEAN_DRAFT)
    assert rep["issues"] and rep["issues"][0]["severity"] == "critical"
    assert not rep.get("unparseable")


@pytest.mark.parametrize("junk", [
    'My answer is "ruling": "approve" but <<< broken beyond repair >>>',
    '{"ruling": "approve" <<< broken beyond repair >>> }{',
])
def test_an_unreadable_approval_is_never_salvaged(junk):
    out = RP.run_panel(_bundle(), CLEAN_DRAFT, slot="school_call",
                       writer_llm=Script([junk]), rounds=1, **QUIET)
    assert out["approved"] is False
    assert out["rounds"][0]["ruling"]["ruling"] == "revise"


def test_a_garbled_reject_is_still_a_reject():
    junk = '{"ruling": "reject" <<< broken beyond repair >>> }{'
    out = RP.run_panel(_bundle(), CLEAN_DRAFT, slot="school_call",
                       writer_llm=Script([junk]), rounds=1, **QUIET)
    assert out["rounds"][0]["ruling"]["ruling"] == "reject"


def test_llm_records_max_tokens_and_the_stop_reason(monkeypatch):
    seen = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        seen["body"] = json.loads(req.data.decode())
        return Resp(json.dumps({"content": [{"type": "text", "text": "hi"}],
                                "stop_reason": "max_tokens"}).encode())

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    llm = RF._llm_from_env(temperature=0.2, max_tokens=4000)
    assert llm.last_stop_reason is None
    assert llm([{"role": "system", "content": "s"},
                {"role": "user", "content": "u"}]) == "hi"
    assert seen["body"]["max_tokens"] == 4000
    assert llm.last_stop_reason == "max_tokens"
    # The writer keeps its old limit.
    RF._llm_from_env()([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}])
    assert seen["body"]["max_tokens"] == 2000


# --- 2. reviewers that no longer contradict each other -------------------------

BRIEF = ("BAYFIELD (6,900 ft): 2026-09-25T00:00 -> 2026-09-25T05:00: precip 0.02in\n"
         "YOUR OWN GAUGE AND STAKE: NO READING TODAY.")


def _report(**issue):
    base = {"severity": "critical", "quote": "q", "problem": "p",
            "evidence": "", "fix": ""}
    base.update(issue)
    return json.dumps({"verdict": "issues", "issues": [base]})


def test_a_flag_with_no_brief_line_behind_it_is_downgraded():
    s = Script([ok()], facts=_report(evidence="Bayfield gets 0.0in before the school run"))
    rep = RP.fact_check(s, BRIEF, CLEAN_DRAFT)
    assert rep["issues"][0]["severity"] == "minor"
    assert "downgraded" in rep["issues"][0]["problem"]


def test_a_flag_quoting_the_brief_stands():
    s = Script([ok()], facts=_report(
        evidence="2026-09-25T00:00 -> 2026-09-25T05:00: precip 0.02in"))
    assert RP.fact_check(s, BRIEF, CLEAN_DRAFT)["issues"][0]["severity"] == "critical"


def test_evidence_survives_case_and_spacing():
    s = Script([ok()], facts=_report(evidence="your own gauge  and stake: no reading today."))
    assert RP.fact_check(s, BRIEF, CLEAN_DRAFT)["issues"][0]["severity"] == "critical"


@pytest.mark.parametrize("ev", ["NOT IN BRIEF", "not in brief, the draft invented it"])
def test_an_unsupported_claim_needs_no_brief_line(ev):
    s = Script([ok()], facts=_report(evidence=ev))
    assert RP.fact_check(s, BRIEF, CLEAN_DRAFT)["issues"][0]["severity"] == "critical"


def test_a_flag_with_no_evidence_at_all_is_downgraded():
    s = Script([ok()], facts=_report(evidence=""))
    assert RP.fact_check(s, BRIEF, CLEAN_DRAFT)["issues"][0]["severity"] == "minor"


def test_a_minor_issue_needs_no_evidence():
    s = Script([ok()], facts=_report(severity="minor", evidence=""))
    rep = RP.fact_check(s, BRIEF, CLEAN_DRAFT)
    assert rep["issues"][0]["severity"] == "minor"
    assert "downgraded" not in rep["issues"][0]["problem"]


def test_the_editor_is_shown_the_brief():
    s = Script([ok()])
    RP.run_panel(_bundle(), CLEAN_DRAFT, slot="school_call", writer_llm=s,
                 rounds=1, **QUIET)
    editor_user = [c[1] for c in s.calls if c[0] == "editor"][0][-1]["content"]
    assert "DATA BRIEF THE WRITER HAD" in editor_user
    assert "YOUR OWN GAUGE AND STAKE" in editor_user


def test_the_editors_evidence_is_not_checked_against_the_brief():
    """Editor issues are about voice and repetition; their evidence is the
    persona or the recent posts, not the brief."""
    s = Script([ok()], editor=_report(severity="major",
                                      evidence="PERSONA: never reuse a closing question"))
    rep = RP.edit_review(s, CLEAN_DRAFT, _bundle(), [])
    assert rep["issues"][0]["severity"] == "major"


ALL_THREE = {"fact checker": RP.FACT_CHECKER_SYSTEM,
             "editor": RP.EDITOR_SYSTEM,
             "magistrate": RP.MAGISTRATE_SYSTEM}


@pytest.mark.parametrize("who", list(ALL_THREE))
def test_every_role_carries_the_same_binding_rules(who):
    p = ALL_THREE[who]
    assert RP.SHARED_RULES in p
    for phrase in ("THE STAMP", "CONTAINS the brief's figure", "GUST UNITS",
                   "NO INVENTION IN A FIX", "the fact checker wins on numbers"):
        assert phrase in p


@pytest.mark.parametrize("who", list(ALL_THREE))
def test_every_role_is_told_to_escape_quotes(who):
    assert '\\"' in ALL_THREE[who]


@pytest.mark.parametrize("who", list(ALL_THREE))
def test_no_role_may_read_composed_at_as_evidence_about_the_stamp(who):
    """2026-09-25: the fact checker and the magistrate both called a correct
    5:52am stamp fabricated "when composed at 9:56pm", and the magistrate
    rejected a sound post partly on that. The old rule said only "never flag
    it as fabricated" without saying where the clock time comes from, so the
    reasoning had nothing to run into.
    """
    rule = [ln for ln in ALL_THREE[who].splitlines() if ln.startswith("2. THE STAMP")]
    assert len(rule) == 1
    rule = rule[0]
    assert "COMPOSED AT is NOT evidence" in rule
    assert "evening run writes the next morning's post" in rule
    assert "fabricated" in rule


# --- 3. the gauge reading nobody entered ------------------------------------------

def test_the_persona_no_longer_offers_a_bare_gauge_number_as_the_model_detail():
    persona = CO.load_system_prompt()
    assert "Only when the brief's gauge block carries a reading" in persona
    assert "NO READING TODAY" in persona
    # The old unconditional line is gone.
    assert '"The gauge showed 0.12 overnight" works. "It' not in persona


def test_the_no_reading_block_forbids_the_gauge_verbs():
    out = CO.render_bundle({"home_gauge": None})
    assert "NO READING TODAY" in out
    assert "the gauge caught / showed / read" in out
    assert "reviewer's suggested wording" in out


def test_the_reviser_is_told_not_to_use_an_invented_figure():
    assert "not in your brief" in RP.REVISER_INSTRUCTION
    assert "assigned stamp" in RP.REVISER_INSTRUCTION


def test_an_invented_gauge_line_in_a_fix_never_reaches_the_published_text():
    """End to end: the editor suggests the invented line, the reviser obeys it,
    and the rule gate still refuses the result. The panel cannot approve it."""
    invented = CLEAN_DRAFT.replace(
        "How is it looking out your window?",
        "The gauge caught 0.08 overnight, how is it looking out your window?")
    editor = json.dumps({"verdict": "issues", "issues": [
        {"severity": "major", "quote": "How is it looking out your window?",
         "problem": "reused closer", "evidence": "PERSONA",
         "fix": "The gauge caught 0.08 overnight and the sky's heavy."}]})
    s = Script([revise("closer -> The gauge caught 0.08 overnight"), ok()],
               editor=editor, writer=[invented])
    out = RP.run_panel(_bundle(), CLEAN_DRAFT, slot="school_call", writer_llm=s,
                       rounds=2, **QUIET)
    assert out["approved"] is False
    assert out["rounds"][1]["gate"][0] == "block"
    assert any("gauge" in r for r in out["rounds"][1]["gate"][1])
