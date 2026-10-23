"""scripts/push_state.py: race-safe state pushes now that emergency-alert has its own
concurrency group. Offline; the git tests use a local bare repo and skip without git."""
import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import push_state as PS  # noqa: E402


def post(pid, checked=False):
    return {"post_id": pid, "engagement_checked": checked, "engagement": {"likes": 3} if checked else None}


def test_merge_is_a_union_by_post_id_remote_order_first():
    theirs = {"posts": [post("a"), post("b")]}
    ours = {"posts": [post("a"), post("c")]}
    assert [p["post_id"] for p in PS.merge_post_history(ours, theirs)["posts"]] == ["a", "b", "c"]


def test_merge_keeps_checked_engagement_from_either_side():
    assert PS.merge_post_history({"posts": [post("a")]}, {"posts": [post("a", True)]})["posts"] == [post("a", True)]
    assert PS.merge_post_history({"posts": [post("a", True)]}, {"posts": [post("a")]})["posts"] == [post("a", True)]


def test_merge_tolerates_garbage():
    assert PS.merge_post_history(None, {"posts": [post("a"), "junk"]})["posts"] == [post("a")]
    assert PS.merge_post_history({"posts": [{"x": 1}]}, {})["posts"] == [{"x": 1}]


needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def clone(remote, path):
    git(path.parent, "clone", "-q", str(remote), path.name)
    git(path, "config", "user.name", "t")
    git(path, "config", "user.email", "t@example.com")
    return path


def write(repo, rel, data):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n")


@pytest.fixture
def repos(tmp_path):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    seed = clone(remote, tmp_path / "seed")
    git(seed, "checkout", "-q", "-b", "main")
    write(seed, "state/post_history.json", {"posts": [post("old")]})
    write(seed, "state/emergency_alert_state.json", {"n": 0})
    git(seed, "add", ".")
    git(seed, "commit", "-q", "-m", "seed")
    git(seed, "push", "-q", "origin", "main")
    return remote, clone(remote, tmp_path / "a"), clone(remote, tmp_path / "b")


@needs_git
def test_two_writers_of_post_history_both_land(repos, monkeypatch):
    remote, a, b = repos
    # emergency (a) and daily-post (b) each append a post from the same starting point
    write(a, "state/post_history.json", {"posts": [post("old"), post("alert")]})
    write(a, "state/emergency_alert_state.json", {"n": 1})
    write(b, "state/post_history.json", {"posts": [post("old"), post("daily")]})
    monkeypatch.chdir(b)
    assert PS.push_state("daily", ["state/post_history.json"], branch="main", sleep=lambda s: None) == 0
    monkeypatch.chdir(a)
    assert PS.push_state("emergency", ["state/post_history.json", "state/emergency_alert_state.json"],
                         branch="main", sleep=lambda s: None) == 0
    git(b, "pull", "-q", "origin", "main")
    hist = json.loads((b / "state/post_history.json").read_text())
    assert [p["post_id"] for p in hist["posts"]] == ["old", "daily", "alert"]
    assert json.loads((b / "state/emergency_alert_state.json").read_text()) == {"n": 1}


@needs_git
def test_nothing_to_commit_is_success(repos, monkeypatch):
    _remote, a, _b = repos
    monkeypatch.chdir(a)
    assert PS.push_state("noop", ["state/post_history.json"], branch="main", sleep=lambda s: None) == 0
    assert git(a, "log", "--oneline").count("\n") == 1


@needs_git
def test_gives_up_when_the_remote_is_gone(repos, monkeypatch, tmp_path):
    remote, a, _b = repos
    write(a, "state/post_history.json", {"posts": [post("x")]})
    shutil.rmtree(remote)
    monkeypatch.chdir(a)
    assert PS.push_state("x", ["state/post_history.json"], branch="main", sleep=lambda s: None) == 1
