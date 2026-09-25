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

THIS FILE IS DEVELOPER-FACING. No workflow runs pytest -- `npm test` in
daily-audit.yml is the only suite CI runs -- so these checks fire when someone
changing the rules runs the suite, not automatically. That is deliberate: the
same check lived in `npm test` briefly, and `npm test` GATES the audit step, so
one flagged post would have killed the daily audit rather than reporting the
problem. An alarm must not be silenced by the thing it exists to report.

Refresh the baseline with tests/fixtures/road_baseline_refresh.py after an
intended change, and read the diff -- that diff is the review.
"""

import glob
import importlib.util
import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from wx import guardrails as G  # noqa: E402

REPO = os.path.join(os.path.dirname(__file__), "..")
FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
BASELINE = os.path.join(FIXTURES, "road_baseline.json")


def _load_refresh():
    """The generator is imported, not reimplemented.

    An earlier cut copied its front-matter splitter into this file, so the
    baseline's author and its checker could have drifted on how a draft is
    parsed and still agreed on every verdict. Importing means the thing under
    test is the thing that wrote the file.
    """
    path = os.path.join(FIXTURES, "road_baseline_refresh.py")
    spec = importlib.util.spec_from_file_location("_road_baseline_refresh", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REFRESH = _load_refresh()

with open(BASELINE, encoding="utf-8") as _fh:
    DRAFTS = json.load(_fh)["drafts"]


def test_nothing_that_published_is_flagged():
    """site/weather/ is copy the gate already passed. Flagging it is a bug."""
    posts = sorted(glob.glob(os.path.join(REPO, "site", "weather", "2*.md")))
    assert posts, "no published posts found -- has the layout moved?"
    flagged = []
    for path in posts:
        stated, why = G.road_status_claim(REFRESH.body(path))
        if stated:
            flagged.append(f"  {os.path.basename(path)}\n"
                           f"    {why}: {stated!r}")
    assert not flagged, (
        f"{len(flagged)} of {len(posts)} published posts are now flagged. "
        "These went out through the gate, so this is a false positive on known "
        "good copy:\n" + "\n".join(flagged))


def test_the_linter_agrees_on_the_published_posts():
    """The other gate, over the same real copy.

    tools/fixtures/road-cases.json already pins both gates to 59 constructed
    sentences; this is the same question asked of prose nobody wrote for a
    test.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed; `npm test` covers the linter")
    lint = os.path.join(REPO, "tools", "draft-lint.mjs")
    flagged = []
    for path in sorted(glob.glob(os.path.join(REPO, "site", "weather", "2*.md"))):
        name = os.path.basename(path)
        out = subprocess.run([node, lint, path, f"--date={name[:10]}",
                              "--history=none", "--json"],
                             capture_output=True, text=True)
        if out.returncode == 2:
            continue
        for rule, detail in json.loads(out.stdout)["fails"]:
            if rule == "road-status":
                flagged.append(f"  {name}\n    {detail}")
    assert not flagged, ("draft-lint.mjs flags published posts:\n"
                         + "\n".join(flagged))


def test_the_recorded_drafts_match_the_baseline():
    """A rule change shows up as a sentence diff, not as a count."""
    present = {k: v for k, v in REFRESH.scan().items() if k in DRAFTS}
    assert present, "every baselined draft has disappeared"

    wrong = []
    for rel, got in sorted(present.items()):
        if got != DRAFTS[rel]:
            wrong.append(f"  {rel}\n    baseline: {DRAFTS[rel]!r}\n"
                         f"    now:      {got!r}")
    assert not wrong, (
        "the road rules changed what they say about recorded drafts:\n"
        + "\n".join(wrong)
        + "\n\nIf that was intended, run "
          "tests/fixtures/road_baseline_refresh.py and read the diff.")


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
