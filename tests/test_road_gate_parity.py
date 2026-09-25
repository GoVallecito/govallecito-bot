"""The publishing gate against the shared road corpus.

tools/fixtures/road-cases.json is read by this file AND by
tools/draft-lint.test.mjs, so guardrails.py and draft-lint.mjs cannot drift
apart on these sentences without one of the two suites going red. Where they
disagree, scripts/wx/prompts/system.md decides and the linter is the one that
is wrong -- both of those files say so.

The road rules are shallow syntax done with regexes, so a change that looks
local usually is not: five review rounds on PR #37 found 31 defects, roughly
two thirds of them regressions introduced by the previous round's fix. Add a
case to the JSON rather than to one suite.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from wx import guardrails as G  # noqa: E402

CORPUS = os.path.join(os.path.dirname(__file__), "..", "tools", "fixtures",
                      "road-cases.json")

with open(CORPUS, encoding="utf-8") as _fh:
    CASES = json.load(_fh)["cases"]


def _verdict(text):
    stated, _ = G.road_status_claim(text)
    return "claim" if stated else "clean"


def test_the_corpus_is_well_formed():
    """A typo in the JSON must not quietly reduce the coverage."""
    assert len(CASES) >= 50, "the corpus should not shrink"
    for case in CASES:
        assert case["verdict"] in ("claim", "clean"), case
        assert case["text"].strip(), case
        assert case["note"].strip(), f"every case says what it guards: {case}"
    texts = [c["text"] for c in CASES]
    assert len(texts) == len(set(texts)), "duplicate case"


def test_the_gate_agrees_with_the_corpus():
    """Both directions matter, and the false-positive one matters more.

    A missed claim is a bad post. A false flag on correct copy cannot be
    repaired by the rewrite loop -- there is nothing wrong with the sentence --
    so it burns the morning, which is the failure the whole rebuild exists to
    stop.
    """
    wrong = []
    for case in CASES:
        got = _verdict(case["text"])
        if got != case["verdict"]:
            wrong.append(f"  wanted {case['verdict']:5} got {got:5} "
                         f"{case['text']!r}\n      {case['note']}")
    assert not wrong, ("the publishing gate disagrees with "
                       "tools/fixtures/road-cases.json:\n" + "\n".join(wrong))


def test_the_probe_the_node_suite_uses_reports_the_same_thing():
    """tools/road-gate-probe.py is how `npm test` reaches this gate.

    npm test is the only suite CI runs, so if the probe stops matching this
    module the cross-gate check silently becomes a no-op there.
    """
    import subprocess

    probe = os.path.join(os.path.dirname(__file__), "..", "tools",
                         "road-gate-probe.py")
    out = subprocess.run([sys.executable, probe, CORPUS],
                         capture_output=True, text=True, check=True)
    results = json.loads(out.stdout)["results"]
    assert len(results) == len(CASES)
    for case, result in zip(CASES, results):
        assert result["text"] == case["text"]
        assert result["verdict"] == _verdict(case["text"])
