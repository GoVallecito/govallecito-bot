#!/usr/bin/env python3
"""Rewrite tests/fixtures/road_baseline.json from the current road rules.

Run this ONLY after an intended behaviour change, and read the diff before
committing it. The diff is the review: it shows, in the forecaster's own
sentences, what the change did to every draft this repo has recorded.

    python3 tests/fixtures/road_baseline_refresh.py
    git diff tests/fixtures/road_baseline.json

Reads state/drafts/ and site/weather/_pending/ and writes nothing but the
baseline. It never edits state/ -- see CLAUDE.md.
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
BASELINE = os.path.join(HERE, "road_baseline.json")
SOURCES = ("state/drafts/*.md", "site/weather/_pending/*.md")

sys.path.insert(0, os.path.join(REPO, "scripts"))
from wx import guardrails as G  # noqa: E402


def body(path):
    """The post text, past either on-disk front-matter shape."""
    raw = open(path, encoding="utf-8").read()
    if raw.startswith("# "):
        return raw.split("\n---\n", 1)[-1]
    return raw.split("\n---", 1)[-1]


def scan():
    entries = {}
    for pattern in SOURCES:
        for path in sorted(glob.glob(os.path.join(REPO, pattern))):
            rel = os.path.relpath(path, REPO).replace(os.sep, "/")
            stated, why = G.road_status_claim(body(path))
            entries[rel] = ({"flagged": True, "sentence": stated, "why": why}
                            if stated else {"flagged": False})
    return entries


def main():
    with open(BASELINE, encoding="utf-8") as fh:
        doc = json.load(fh)
    before = doc["drafts"]
    after = scan()

    changed = [k for k in sorted(set(before) | set(after))
               if before.get(k) != after.get(k)]
    doc["drafts"] = after
    with open(BASELINE, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    flagged = sum(1 for v in after.values() if v["flagged"])
    print(f"{len(after)} drafts, {flagged} flagged, {len(after) - flagged} clean")
    if not changed:
        print("no change")
        return 0
    print(f"{len(changed)} changed -- read each one before committing:")
    for key in changed:
        was, now = before.get(key), after.get(key)
        print(f"  {key}")
        print(f"    was: {was!r}")
        print(f"    now: {now!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
