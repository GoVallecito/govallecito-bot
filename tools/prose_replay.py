#!/usr/bin/env python3
"""Measure the prose gate and the splice guard against everything on record.

Offline: no network, no model call, nothing written. Two questions:

  1. Which saved texts would guardrails.prose_damage() block? Checked over
     site/weather/ (published), site/weather/_pending/ (held) and
     state/drafts/ (every draft the writer produced).
  2. Which substitutions recorded in state/panel/*.md would
     review_panel._splice_is_safe() now drop? The transcript keeps the quote
     and the fix but not the text around them, so the seam is reconstructed as
     `quote + ", and the rest of the sentence carried on."`: the question is
     whether the fix would have been safe had the sentence continued.

    python tools/prose_replay.py            report
    python tools/prose_replay.py --strict   exit 1 if anything on the site blocks
"""

import argparse
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "scripts"))

from wx import guardrails as G        # noqa: E402
from wx import review_panel as RP     # noqa: E402

CORPORA = (
    ("published", os.path.join("site", "weather", "*.md")),
    ("pending", os.path.join("site", "weather", "_pending", "*.md")),
    ("drafts", os.path.join("state", "drafts", "*.md")),
)

# - [minor, editor] "quote" -> "fix"      (applied)
# - [editor] "quote" -> "fix"             (dropped at the seam)
SUBSTITUTION = re.compile(r'^- \[([^\]]+)\] "(.*)" -> "(.*)"\s*$')
CONTINUATION = ", and the rest of the sentence carried on."


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def blocked_texts():
    """{label: (total, [(filename, damage), ...])}"""
    out = {}
    for label, pattern in CORPORA:
        files = sorted(glob.glob(os.path.join(REPO, pattern)))
        hits = []
        for path in files:
            damage = G.prose_damage(_read(path))
            if damage:
                hits.append((os.path.basename(path), damage))
        out[label] = (len(files), hits)
    return out


def replayed_substitutions():
    """(total, [(filename, who, quote, fix), ...]) for the ones now dropped."""
    total, dropped = 0, []
    for path in sorted(glob.glob(os.path.join(REPO, "state", "panel", "*.md"))):
        for line in _read(path).splitlines():
            m = SUBSTITUTION.match(line)
            if not m:
                continue
            who, quote, fix = m.groups()
            total += 1
            if not RP._splice_is_safe(quote + CONTINUATION, quote, fix):
                dropped.append((os.path.basename(path), who, quote, fix))
    return total, dropped


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if anything currently on the site would block")
    args = ap.parse_args(argv)

    texts = blocked_texts()
    for label, (total, hits) in texts.items():
        print(f"{label}: {len(hits)} of {total} would block")
        for name, damage in hits:
            for symptom, evidence in damage:
                print(f"  {name}: {symptom} ({evidence!r})")

    total, dropped = replayed_substitutions()
    print(f"substitutions: {len(dropped)} of {total} recorded would now be dropped")
    for name, who, quote, fix in dropped:
        print(f"  {name} [{who}]: {quote!r} -> {fix!r}")

    on_site = len(texts["published"][1]) + len(texts["pending"][1])
    if args.strict and on_site:
        print(f"STRICT: {on_site} text(s) currently on the site would block")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
