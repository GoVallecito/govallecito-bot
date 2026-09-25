#!/usr/bin/env python3
"""Replay every recorded draft through the publishing gate at two revisions.

Unit tests ask what someone thought to ask. This asks what the gate does to
prose the forecaster actually wrote, at two points in history, and prints the
difference. It is how the road-status work in PRs #35 and #37 was checked.

    python3 tools/gate-diff.py                      # pre-#35 vs working tree
    python3 tools/gate-diff.py --before HEAD~1      # last commit vs working tree
    python3 tools/gate-diff.py --before v1 --after v2

Offline and free: no model call, no network, no API key. The gate is pure
text analysis, so `guardrails.evaluate()` runs on a fixed in-memory bundle and
the only variable is the draft text and the rules themselves.

THE CORPUS IS ALWAYS THE WORKING TREE'S. Only the RULES come from the two
revisions -- comparing both rules and both sets of drafts would confound the
two, and the question is always "what would today's rules have said about the
drafts we have".

Exit 1 when the "after" side flags a post that PUBLISHED. Those went out
through the gate, so a flag is a false positive on known-good copy, and a
false flag cannot be repaired by the rewrite loop -- there is nothing wrong
with the sentence -- so it burns the morning. That is the one outcome worth
failing a command over.

Reads state/ and site/ and never writes them; scratch goes to a temp dir.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The commit before PR #35, which is where the road-status work starts. Any
# rev works; this is only the default.
DEFAULT_BEFORE = "2c3c6a1"

SOURCES = ("state/drafts/*.md", "site/weather/_pending/*.md",
           "site/weather/2*.md")

# Everything the gate needs present, so the only thing under test is what it
# says about the TEXT rather than about a thin bundle.
BUNDLE = {
    "missing": [],
    "bands": {b: {"ok": True} for b in
              ("durango", "bayfield", "vallecito", "weminuche")},
    "life_safety_alerts": [],
    "snow_line": None,
}


def body(path):
    """The post text, past either on-disk front-matter shape."""
    raw = open(path, encoding="utf-8").read()
    if raw.startswith("# "):
        return raw.split("\n---\n", 1)[-1]
    return raw.split("\n---", 1)[-1]


def group(rel):
    if rel.startswith("site/weather/_pending/"):
        return "held (_pending)"
    if rel.startswith("state/drafts/"):
        return "held (state/drafts)"
    return "PUBLISHED"


# --- the probe -------------------------------------------------------------
#
# Runs in its own process so two versions of the `wx` package can be imported
# without colliding on the module name.

def probe(scripts_dir):
    sys.path.insert(0, scripts_dir)
    from wx import guardrails as G

    out = {}
    for pattern in SOURCES:
        for path in sorted(glob.glob(os.path.join(REPO, pattern))):
            rel = os.path.relpath(path, REPO).replace(os.sep, "/")
            verdict, reasons = G.evaluate(BUNDLE, body(path),
                                          first_30_days=False)
            road = [r for r in reasons
                    if "road" in r.lower() or "CDOT" in r]
            out[rel] = {"verdict": verdict,
                        "road": road[0] if road else None,
                        "fixable": G.text_fixable(reasons) if reasons else False}
    json.dump(out, sys.stdout)


def run_probe(scripts_dir, label):
    result = subprocess.run([sys.executable, os.path.abspath(__file__),
                             "--probe", scripts_dir],
                            capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"probing {label} failed:\n{result.stderr}")
    return json.loads(result.stdout)


def scripts_at(rev, workdir):
    """Extract scripts/ at `rev`, or point at the working tree for None."""
    if rev is None:
        return os.path.join(REPO, "scripts")
    dest = os.path.join(workdir, rev.replace("/", "_"))
    os.makedirs(dest, exist_ok=True)
    archive = subprocess.run(["git", "-C", REPO, "archive", rev, "scripts"],
                             capture_output=True)
    if archive.returncode != 0:
        sys.exit(f"git archive {rev} failed: "
                 f"{archive.stderr.decode(errors='replace').strip()}")
    tar = subprocess.run(["tar", "-x", "-C", dest], input=archive.stdout,
                         capture_output=True)
    if tar.returncode != 0:
        sys.exit(f"extracting {rev} failed: "
                 f"{tar.stderr.decode(errors='replace').strip()}")
    return os.path.join(dest, "scripts")


# --- reporting -------------------------------------------------------------

def report(before, after, before_label, after_label):
    rule = "=" * 74
    print(rule)
    print(f"ROAD CLAIMS THE GATE CAUGHT   {before_label}  ->  {after_label}")
    print(rule)
    for name in ("PUBLISHED", "held (_pending)", "held (state/drafts)"):
        keys = [k for k in after if group(k) == name]
        if not keys:
            continue
        was = sum(1 for k in keys if before.get(k, {}).get("road"))
        now = sum(1 for k in keys if after[k]["road"])
        print(f"  {name:22} n={len(keys):2}   before: {was:2}   after: {now:2}")

    newly, no_longer = [], []
    for key in sorted(after):
        was = bool(before.get(key, {}).get("road"))
        now = bool(after[key]["road"])
        if now and not was:
            newly.append(key)
        elif was and not now:
            no_longer.append(key)

    for title, keys, side in (("NEWLY CAUGHT", newly, after),
                              ("NO LONGER CAUGHT", no_longer, before)):
        print()
        print(rule)
        print(f"{title}  ({len(keys)})")
        print(rule)
        if not keys:
            print("  none")
        for key in keys:
            entry = side[key]
            print(f"  {key}")
            if entry.get("road"):
                print(f"    {entry['road'][:150]}")
            if title == "NEWLY CAUGHT":
                print(f"    verdict {entry['verdict']}, "
                      f"rewritable: {entry['fixable']}")

    regressions = [k for k in newly if group(k) == "PUBLISHED"]
    print()
    print(rule)
    if regressions:
        print(f"FAIL: {len(regressions)} PUBLISHED post(s) newly flagged.")
        print("These went out through the gate, so this is a false positive on")
        print("known good copy -- and the rewrite loop cannot repair a sentence")
        print("that was already correct.")
        for key in regressions:
            print(f"  {key}")
        return 1
    print("OK: no published post is newly flagged.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Diff the publishing gate across two revisions.")
    parser.add_argument("--probe", metavar="SCRIPTS_DIR",
                        help=argparse.SUPPRESS)
    parser.add_argument("--before", default=DEFAULT_BEFORE,
                        help=f"baseline rev (default {DEFAULT_BEFORE}, the "
                             "commit before PR #35)")
    parser.add_argument("--after", default=None,
                        help="rev to compare (default: the working tree)")
    args = parser.parse_args()

    if args.probe:
        probe(args.probe)
        return 0

    workdir = tempfile.mkdtemp(prefix="gate-diff-")
    try:
        before = run_probe(scripts_at(args.before, workdir), args.before)
        after = run_probe(scripts_at(args.after, workdir),
                          args.after or "working tree")
        return report(before, after, args.before,
                      args.after or "working tree")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
