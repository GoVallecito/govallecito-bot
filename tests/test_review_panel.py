"""
The review panel: fact checker + editor -> magistrate, looping, and the only
path to an unattended website publish. No network, no model: every role is a
scripted callable.
"""
import glob
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))

import pytest

from test_runners import CLEAN_DRAFT, _fakes
from wx import bundle as B, verify as V
from wx import review_panel as RP
from wx import run_forecast as RF
from wx import site as SITE

REVISED = CLEAN_DRAFT.replace("How is it looking out your window?",
                              "Anybody up the Florida already chaining up?")
ROAD_CLAIM = CLEAN_DRAFT + " The passes are dry this morning."


class Script:
    """Routes each call by role, from its system prompt, and records it."""

    def __init__(self, rulings, facts=None, editor=None, writer=None):
        self.rulings = list(rulings)
        self.facts = facts or '{"verdict": "clean", "issues": []}'
        self.editor = editor or '{"verdict": "clean", "issues": []}'
        self.writer = list(writer or [])
        self.calls = []

    def __call__(self, messages):
        system = next(m["content"] for m in messages if m["role"] == "system")
        if system.startswith("You are the fact checker"):
            role, out = "facts", self.facts
        elif system.startswith("You are the editor"):
            role, out = "editor", self.editor
        elif system.startswith("You are the magistrate"):
            role = "magistrate"
            r = self.rulings.pop(0) if len(self.rulings) > 1 else self.rulings[0]
            out = json.dumps(r) if isinstance(r, dict) else r
        else:
            role = "writer"
            out = self.writer.pop(0) if self.writer else CLEAN_DRAFT
        self.calls.append((role, messages))
        return out

    def roles(self):
        return [c[0] for c in self.calls]


def ok(title="Snow on the Florida"):
    return {"ruling": "approve", "required_changes": [], "dismissed": [],
            "title": title, "rationale": "Supported by the brief, reads right."}


def revise(*changes):
    return {"ruling": "revise", "required_changes": list(changes),
            "dismissed": [], "title": "", "rationale": "Fix the closer."}


REJECT = {"ruling": "reject", "required_changes": [], "dismissed": [],
          "title": "", "rationale": "The data contradicts itself."}


@pytest.fixture
def panel_on(monkeypatch):
    monkeypatch.setenv("WX_REVIEW_PANEL", "true")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("FB_GROUP_ID", raising=False)


def _run(script, d, first_30_days=True, bundle=None):
    V.FORECAST_LOG = os.path.join(d, "log.json")
    V.CALIBRATION = os.path.join(d, "cal.json")
    os.chdir(d)
    return RF.run(slot="school_call", llm=script, review_llm=script,
                  first_30_days=first_30_days,
                  dry_bundle=bundle or B.build(fetchers=_fakes()), site_dir=d)


def _feed(d):
    p = os.path.join(d, SITE.FEED_NAME)
    return json.load(open(p)) if os.path.exists(p) else None


# --- the runner -----------------------------------------------------------------

def test_first_round_approval_publishes_to_the_site_with_no_human(panel_on):
    s = Script([ok()])
    with tempfile.TemporaryDirectory() as d:
        assert _run(s, d) == 0
        feed = _feed(d)
        assert feed and feed["count"] == 1
        assert feed["posts"][0]["title"] == "Snow on the Florida"
        assert not glob.glob(os.path.join(d, "_pending", "*.md")), "nothing staged"
        assert glob.glob(os.path.join(d, "state", "panel", "*.md")), "transcript kept"
        status = open(os.path.join(d, "state", "forecast-status.md")).read()
        assert "approved by review panel" in status
    assert s.roles() == ["writer", "facts", "editor", "magistrate"]


def test_revise_then_approve_publishes_the_revised_text(panel_on):
    s = Script([revise('"How is it looking out your window?" -> a new closer'), ok()],
               writer=[CLEAN_DRAFT, REVISED])
    with tempfile.TemporaryDirectory() as d:
        assert _run(s, d) == 0
        body = SITE.read_post(glob.glob(os.path.join(d, "20*.md"))[0])["body"]
        assert "chaining up" in body and "out your window" not in body
    # the reviser was handed the magistrate's exact change
    reviser_msgs = [c[1] for c in s.calls if c[0] == "writer"][1]
    assert "a new closer" in reviser_msgs[-1]["content"]
    assert s.roles().count("magistrate") == 2


def test_never_approved_is_held_not_published(panel_on):
    s = Script([revise("change the closer")])
    with tempfile.TemporaryDirectory() as d:
        assert _run(s, d) == 0
        assert _feed(d) is None, "nothing may reach the feed without approval"
        assert glob.glob(os.path.join(d, "_pending", "*.md")), "staged for a human"
        status = open(os.path.join(d, "state", "forecast-status.md")).read()
        assert "not approved after 3 round" in status
    assert s.roles().count("magistrate") == 3


def test_reject_stops_the_loop_and_holds(panel_on):
    s = Script([REJECT])
    with tempfile.TemporaryDirectory() as d:
        assert _run(s, d) == 0
        assert _feed(d) is None
        assert glob.glob(os.path.join(d, "_pending", "*.md"))
    assert s.roles().count("magistrate") == 1


def test_magistrate_cannot_approve_text_the_rule_gate_blocks(panel_on):
    # The writer keeps producing a present-tense road claim and the magistrate
    # keeps approving it. The gate wins every round.
    s = Script([ok()], writer=[ROAD_CLAIM] * 10)
    with tempfile.TemporaryDirectory() as d:
        assert _run(s, d) == 0
        assert _feed(d) is None


def test_facebook_stays_off_while_first_30_days(panel_on, monkeypatch):
    posted = []
    monkeypatch.setattr(RF.P, "post_to_page", lambda *a, **k: posted.append(1) or {})
    monkeypatch.setattr(RF.P, "post_photo_to_page",
                        lambda *a, **k: posted.append(1) or {})
    with tempfile.TemporaryDirectory() as d:
        assert _run(Script([ok()]), d, first_30_days=True) == 0
    assert posted == []
    with tempfile.TemporaryDirectory() as d:
        assert _run(Script([ok()]), d, first_30_days=False) == 0
    assert posted == [1]


def test_manual_dry_run_does_not_publish_the_site(panel_on, monkeypatch):
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    with tempfile.TemporaryDirectory() as d:
        assert _run(Script([ok()]), d) == 0
        assert _feed(d) is None


def test_panel_off_keeps_the_old_human_gate(monkeypatch):
    monkeypatch.setenv("WX_REVIEW_PANEL", "false")
    with tempfile.TemporaryDirectory() as d:
        assert _run(Script([ok()]), d, first_30_days=True) == 0
        assert _feed(d) is None
        assert glob.glob(os.path.join(d, "_pending", "*.md"))


# --- the loop, directly -------------------------------------------------------------

def _bundle():
    return B.build(fetchers=_fakes())


def test_unreadable_reviewer_withholds_approval():
    s = Script([ok()], facts="I think it's fine!")
    out = RP.run_panel(_bundle(), CLEAN_DRAFT, slot="school_call",
                       writer_llm=s, rounds=2, log=lambda *_: None)
    assert out["approved"] is False
    assert "Approval withheld" in out["rounds"][0]["ruling"]["rationale"]


def test_fenced_json_is_read():
    s = Script(["```json\n" + json.dumps(ok()) + "\n```"])
    out = RP.run_panel(_bundle(), CLEAN_DRAFT, slot="school_call",
                       writer_llm=s, log=lambda *_: None)
    assert out["approved"] is True


def test_reviewer_issues_reach_the_magistrate():
    facts = json.dumps({"verdict": "issues", "issues": [
        {"severity": "critical", "quote": "picked up a few inches",
         "problem": "brief shows no snow at 7,650 ft", "fix": "drop it"}]})
    s = Script([ok()], facts=facts)
    RP.run_panel(_bundle(), CLEAN_DRAFT, slot="school_call", writer_llm=s,
                 log=lambda *_: None)
    mag = [c[1] for c in s.calls if c[0] == "magistrate"][0]
    assert "brief shows no snow at 7,650 ft" in mag[-1]["content"]


def test_transcript_records_every_round():
    s = Script([revise("x -> y"), ok()], writer=[REVISED])
    out = RP.run_panel(_bundle(), CLEAN_DRAFT, slot="school_call",
                       writer_llm=s, log=lambda *_: None)
    md = RP.transcript(out, _bundle(), "school_call")
    assert "## Round 1" in md and "## Round 2" in md and "APPROVED" in md


@pytest.mark.parametrize("raw,expected", [
    ("Snow on the Florida", "Snow on the Florida"),
    ("Snow line near 14,100 ft", ""),
    ("Wet", ""),
    ("**Dry Saturday**: watching Tuesday", "Dry Saturday watching Tuesday"),
])
def test_titles_are_cleaned(raw, expected):
    assert RP._clean_title(raw) == expected


# --- found in review: failure paths must not lose or fake a post -------------------

def test_dry_run_approval_leaves_the_day_open(panel_on, monkeypatch):
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    with tempfile.TemporaryDirectory() as d:
        assert _run(Script([ok()]), d) == 0
        status = open(os.path.join(d, "state", "forecast-status.md")).read()
        assert "NOT published" in status
        assert not os.path.exists(os.path.join(d, "state", "post_ledger.json")) or \
            "school_call" not in open(os.path.join(d, "state", "post_ledger.json")).read()


def test_failed_site_publish_falls_back_to_a_human(panel_on, monkeypatch):
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(RF.SITE, "publish", boom)
    with tempfile.TemporaryDirectory() as d:
        assert _run(Script([ok()]), d) == 0
        assert glob.glob(os.path.join(d, "_pending", "*.md")), "approved text kept"
        status = open(os.path.join(d, "state", "forecast-status.md")).read()
        assert "site publish failed" in status


def test_any_panel_exception_holds_instead_of_crashing(panel_on, monkeypatch):
    def boom(*a, **k):
        raise TimeoutError("read timed out")
    monkeypatch.setattr(RF.RP, "run_panel", boom)
    with tempfile.TemporaryDirectory() as d:
        assert _run(Script([ok()]), d) == 0
        assert _feed(d) is None
        assert glob.glob(os.path.join(d, "_pending", "*.md"))


def test_malformed_ruling_fields_do_not_crash():
    s = Script([{"ruling": "approve", "required_changes": 3, "dismissed": "x"}],
               facts='{"verdict": "issues", "issues": "lots"}')
    out = RP.run_panel(_bundle(), CLEAN_DRAFT, slot="school_call",
                       writer_llm=s, log=lambda *_: None)
    assert out["approved"] is True
