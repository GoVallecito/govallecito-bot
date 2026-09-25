#!/usr/bin/env python3
"""Run tools/fixtures/road-cases.json through the PUBLISHING gate.

Exists so tools/draft-lint.test.mjs can check both gates against one corpus.
`npm test` is the only suite CI runs (daily-audit.yml), so without this the
Python side of the road rules would never be checked there.

Deliberately stdlib-only and loaded by path rather than as part of the `wx`
package: guardrails.py imports nothing but `re` at module level, so this runs
on a bare runner with no pip install and no setup-python. If that ever stops
being true, this prints a diagnostic and exits 2 rather than pretending.

    python3 tools/road-gate-probe.py [path/to/road-cases.json]

Prints one JSON object: {"results": [{"text": ..., "verdict": "claim"|"clean",
"why": ...}]}. No network, no model, no API key.
"""

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GUARDRAILS = os.path.join(REPO, "scripts", "wx", "guardrails.py")


def load_guardrails():
    spec = importlib.util.spec_from_file_location("_wx_guardrails", GUARDRAILS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv):
    corpus = argv[1] if len(argv) > 1 else os.path.join(HERE, "fixtures",
                                                        "road-cases.json")
    try:
        guardrails = load_guardrails()
    except Exception as exc:  # noqa: BLE001 - the diagnostic is the point
        print(f"could not load {GUARDRAILS}: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 2

    with open(corpus, encoding="utf-8") as fh:
        cases = json.load(fh)["cases"]

    results = []
    for case in cases:
        stated, why = guardrails.road_status_claim(case["text"])
        results.append({"text": case["text"],
                        "verdict": "claim" if stated else "clean",
                        "why": why})
    json.dump({"results": results}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
