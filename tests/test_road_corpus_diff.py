"""The road rules against every draft this repo has actually recorded.

tests/test_road_gate_parity.py asks what someone thought to ask. This asks what
the forecaster actually wrote, which catches a different class of mistake: on
PR #37, extending a rule to route numbers and a bare trailing "this" silently
re-broke 2026-09-22 -- one of the four drafts whose lint failure started that
work -- and no unit test noticed. Running the rules over the recorded drafts
did.

Two assertions, and the first is the important one:

  Nothing that PUBLISHED may be flagged. Everything in site/weather/ went out
  through guardrails.evaluate(), so a rule that now flags it has a false
  positive on copy that is known good. A false flag cannot be repaired by the
  rewrite loop -- there is nothing wrong with the sentence -- so it burns the
  morning, which is the failure the whole rebuild exists to stop.

  Held drafts must match tests/fixtures/road_baseline.json, sentence for
  sentence. Only the files listed there are checked, so the workflow commits
  that add a draft every morning do not turn this red.

Refresh the baseline with tests/fixtures/road_baseline_refresh.py after an
intended change, and read the diff -- that diff is the review.
"""

import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from wx import guardrails as G  # noqa: E402

REPO = os.path.join(os.path.dirname(__file__), "..")
BASELINE = os.path.join(os.path.dirname(__file__), "fixtures",
                        "road_baseline.json")

with open(BASELINE, encoding="utf-8") as _fh:
    DRAFTS = json.load(_fh)["drafts"]


def _body(path):
    """The post text, past either on-disk front-matter shape."""
    raw = open(path, encoding="utf-8").read()
    if raw.startswith("# "):
        return raw.split("\n---\n", 1)[-1]
    return raw.split("\n---", 1)[-1]


def test_nothing_that_published_is_flagged():
    """site/weather/ is copy the gate already passed. Flagging it is a bug."""
    posts = sorted(glob.glob(os.path.join(REPO, "site", "weather", "2*.md")))
    assert posts, "no published posts found -- has the layout moved?"
    flagged = []
    for path in posts:
        stated, why = G.road_status_claim(_body(path))
        if stated:
            flagged.append(f"  {os.path.basename(path)}\n"
                           f"    {why}: {stated!r}")
    assert not flagged, (
        f"{len(flagged)} of {len(posts)} published posts are now flagged. "
        "These went out through the gate, so this is a false positive on known "
        "good copy:\n" + "\n".join(flagged))


def test_the_recorded_drafts_match_the_baseline():
    """A rule change shows up as a sentence diff, not as a count."""
    missing, wrong = [], []
    for rel, expected in sorted(DRAFTS.items()):
        path = os.path.join(REPO, rel)
        if not os.path.exists(path):
            missing.append(rel)          # pruned by a workflow; not a failure
            continue
        stated, why = G.road_status_claim(_body(path))
        got = ({"flagged": True, "sentence": stated, "why": why} if stated
               else {"flagged": False})
        if got != expected:
            wrong.append(f"  {rel}\n    baseline: {expected!r}\n"
                         f"    now:      {got!r}")
    assert not wrong, (
        "the road rules changed what they say about recorded drafts:\n"
        + "\n".join(wrong)
        + "\n\nIf that was intended, run "
          "tests/fixtures/road_baseline_refresh.py and read the diff.")
    assert len(missing) < len(DRAFTS), "every baselined draft has disappeared"


def test_the_baseline_still_covers_both_shapes():
    """Its value is the clean half, so guard against it decaying to one side."""
    assert len(DRAFTS) >= 20, "the baseline should not shrink"
    flagged = [k for k, v in DRAFTS.items() if v["flagged"]]
    clean = [k for k, v in DRAFTS.items() if not v["flagged"]]
    assert flagged, "no flagged drafts: the baseline has stopped proving much"
    assert clean, ("no clean drafts: the half that catches false positives is "
                   "gone")
    assert any(k.startswith("state/drafts/") for k in DRAFTS)
    assert any(k.startswith("site/weather/_pending/") for k in DRAFTS)
    for key, entry in DRAFTS.items():
        if entry["flagged"]:
            assert entry.get("sentence", "").strip(), key
            assert entry.get("why", "").strip(), key
