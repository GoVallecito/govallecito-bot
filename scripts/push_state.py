"""
Commit and push workflow state files, safely when another workflow pushes too.

WHY (2026-10-23). emergency-alert.yml now has its own concurrency group, so an
alert no longer queues behind a 15-minute daily or forecast run. That means it can
run at the same time as daily-post.yml or engagement-check.yml, and all three write
state/post_history.json. The old retry (fetch + `git rebase`) stops on the first
conflict, and two runs that each appended one post to that file ALWAYS conflict:
the push then fails five times and a live post loses its record.

So on a rejected push this does not rebase. It keeps this run's copy of each file,
resets to the remote branch, and re-applies:
  * state/post_history.json: MERGED. Posts are the union by post_id (remote order
    first, then this run's new ones); for a post both sides have, the side that
    has checked engagement wins, so engagement-check's data is never undone.
  * every other file: this run's copy. Each of those has one writer workflow, and
    each writer is serialized against itself by its concurrency group.
Then it commits and pushes again, up to ATTEMPTS times.

Usage (from the repo root, git user already configured):
    python scripts/push_state.py "commit message" state/a.json state/b.json
Exit 0 = pushed or nothing to commit, 1 = gave up (the caller prints the error).
"""

import json
import os
import subprocess
import sys
import time

ATTEMPTS = 5
MERGED_FILES = {"state/post_history.json"}


def merge_post_history(ours, theirs):
    """Union of two post_history dicts by post_id. Never drops a post."""
    ours = ours if isinstance(ours, dict) else {}
    theirs = theirs if isinstance(theirs, dict) else {}
    out = dict(theirs)
    posts, index = [], {}
    for p in list(theirs.get("posts") or []) + list(ours.get("posts") or []):
        if not isinstance(p, dict):
            continue
        key = p.get("post_id")
        if key is None:
            posts.append(p)
            continue
        if key not in index:
            index[key] = len(posts)
            posts.append(p)
        elif p.get("engagement_checked") and not posts[index[key]].get("engagement_checked"):
            posts[index[key]] = p
    out["posts"] = posts
    return out


def _git(*args, check=True):
    return subprocess.run(["git", *args], check=check, capture_output=True, text=True)


def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def _reapply(paths, ours):
    """Write this run's file contents over the freshly reset tree (merging where needed)."""
    for path in paths:
        mine = ours.get(path)
        if mine is None:
            continue
        if path in MERGED_FILES:
            theirs_raw = _read(path)
            try:
                theirs = json.loads(theirs_raw) if theirs_raw else {}
                merged = merge_post_history(json.loads(mine), theirs)
                mine = (json.dumps(merged, indent=2) + "\n").encode()
            except ValueError as exc:
                print(f"[push_state] could not merge {path} ({exc}); keeping this run's copy.")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(mine)


def push_state(message, paths, branch=None, sleep=time.sleep):
    branch = branch or os.environ.get("GITHUB_REF_NAME") or _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    existing = [p for p in paths if os.path.exists(p)]
    if existing:
        _git("add", *existing)
    if _git("diff", "--staged", "--quiet", check=False).returncode == 0:
        print("No change to tracked state this run -- nothing to commit.")
        return 0
    _git("commit", "-m", message)
    for attempt in range(1, ATTEMPTS + 1):
        if _git("push", "origin", f"HEAD:{branch}", check=False).returncode == 0:
            print(f"Pushed on attempt {attempt}.")
            return 0
        print(f"Push rejected (attempt {attempt}/{ATTEMPTS}) -- another run pushed first. "
              "Re-applying this run's state on top of the latest remote and retrying...")
        ours = {p: _read(p) for p in paths}
        if _git("fetch", "origin", branch, check=False).returncode != 0:
            sleep(attempt * 5)
            continue
        _git("reset", "--hard", f"origin/{branch}")
        _reapply(paths, ours)
        existing = [p for p in paths if os.path.exists(p)]
        if existing:
            _git("add", *existing)
        if _git("diff", "--staged", "--quiet", check=False).returncode == 0:
            print("The remote already holds this run's state -- nothing left to push.")
            return 0
        _git("commit", "-m", message)
        sleep(attempt * 5)
    return 1


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(push_state(sys.argv[1], sys.argv[2:]))
