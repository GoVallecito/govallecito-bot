"""A smoke test for tools/gate-diff.py.

The tool is how a road-rule change gets checked against real recorded prose
rather than invented cases, so it is worth knowing it still runs. This does
not re-test the gate -- tests/test_road_corpus_diff.py does that -- only that
the driver, the git extraction and the two subprocess probes still fit
together and agree with the rest of the suite.

Skips rather than fails where the environment cannot support it: no git, a
shallow clone without the baseline rev, or no tar. Those are real conditions
in CI checkouts and none of them means the road rules are wrong.
"""

import os
import shutil
import subprocess
import sys

import pytest

REPO = os.path.join(os.path.dirname(__file__), "..")
TOOL = os.path.join(REPO, "tools", "gate-diff.py")


def _have(rev):
    if not shutil.which("git") or not shutil.which("tar"):
        return False
    return subprocess.run(["git", "-C", REPO, "rev-parse", "--verify",
                           f"{rev}^{{commit}}"],
                          capture_output=True).returncode == 0


def _run(*args):
    return subprocess.run([sys.executable, TOOL, *args],
                          capture_output=True, text=True, cwd=REPO)


def test_it_runs_and_reports_no_published_regression():
    """HEAD against the working tree: the corpus is the same, so nothing moves."""
    if not _have("HEAD"):
        pytest.skip("git/tar unavailable or HEAD unresolvable")
    out = _run("--before", "HEAD")
    assert out.returncode == 0, out.stdout + out.stderr
    assert "OK: no published post is newly flagged." in out.stdout
    assert "NEWLY CAUGHT  (0)" in out.stdout, (
        "comparing HEAD to an unchanged working tree should move nothing:\n"
        + out.stdout)


def test_an_unknown_rev_fails_cleanly():
    """A typo should be a message and exit 1, not a traceback."""
    if not shutil.which("git"):
        pytest.skip("git unavailable")
    out = _run("--before", "definitely-not-a-rev")
    assert out.returncode == 1
    assert "not a valid object name" in (out.stdout + out.stderr)
    assert "Traceback" not in (out.stdout + out.stderr)
