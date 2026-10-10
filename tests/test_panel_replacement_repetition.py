"""The panel must not splice in a replacement that echoes a recent post.

WHY THIS EXISTS. On 2026-10-10 the review panel published the pivot "I
wouldn't lock onto any one number", which the 2026-10-09 post had already
published as "so dont lock onto any one total". The editor had rotated off a
retired "grain of salt" hedge and landed straight on yesterday's wording. The
final round splices a reviewer's replacement into the text verbatim, with no
further model call, and nothing asked whether that replacement was a
construction the forecaster had already used.

_echoes_recent is that check. Its thresholds (a 4 word verbatim run, at least
2 of those words rare across the published corpus) came from a backtest of
all 15 published posts: two flags in 237 sentences, both true. A plain
shared-run threshold fails on the zones and weather vocabulary every post
repeats, which is what test 2 pins.

The corpus is faked here (monkeypatched document frequencies) so the repo's
own posts are not fixtures.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from wx import review_panel as RP  # noqa: E402

N_POSTS = 15

# Document frequency over a 15 post corpus: the weather vocabulary is in most
# posts, the construction under test is in one.
COMMON = ["durango", "and", "the", "animas", "valley", "should", "stay",
          "mostly", "dry", "through", "day", "with", "temps", "climbing",
          "into", "mid", "60s", "i", "wouldn't", "any", "one", "number",
          "timing", "window", "shifts", "things", "that's", "whole",
          "ballgame", "for", "totals", "total", "so", "dont", "take", "that",
          "with", "a", "big", "of"]
DF = {w: 10 for w in COMMON}
DF.update({"lock": 1, "onto": 1, "grain": 1, "salt": 1})

ECHO_FIX = ("I wouldn't lock onto any one number, the timing window shifts "
            "things and that's the whole ballgame for totals.")
YESTERDAY = "Timing is shaky, so dont lock onto any one total from the models."

INNOCENT_FIX = ("Durango and the Animas Valley should stay mostly dry through "
                "the day with temps climbing into the mid-60s.")
INNOCENT_PRIOR = ("Yesterday's note: dry through the day with temps climbing "
                  "into the 50s, then clouds.")


def _corpus(monkeypatch, df=None, n=N_POSTS):
    monkeypatch.setattr(RP, "_corpus_df", (dict(df or DF), n))


def test_echo_of_the_1010_pivot_is_named(monkeypatch):
    _corpus(monkeypatch)
    assert RP._echoes_recent(ECHO_FIX, [YESTERDAY]) == "lock onto any one"


def test_long_innocent_run_is_not_an_echo(monkeypatch):
    # A nine word run, all of it weather vocabulary every post repeats. A naive
    # run-length threshold flags this; the rarity weighting must not.
    _corpus(monkeypatch)
    assert len(RP._longest_shared_run(INNOCENT_FIX, INNOCENT_PRIOR)) >= 9
    assert RP._echoes_recent(INNOCENT_FIX, [INNOCENT_PRIOR]) is None


def test_apply_fixes_refuses_an_echoing_replacement(monkeypatch):
    _corpus(monkeypatch)
    quote = "Take that with a big grain of salt."
    fix = "I wouldn't lock onto any one number, the timing window shifts."
    text = f"Morning, its Friday.\n\n{quote}\n\nDid you pull the boat?"
    patched, applied, skipped, unsafe = RP._apply_fixes(
        text, (("editor", {"issues": [
            {"severity": "minor", "quote": quote, "fix": fix}]}),),
        recent_bodies=[YESTERDAY])
    assert patched == text
    assert applied == []
    assert len(unsafe) == 1
    assert "lock onto any one" in unsafe[0]["why"]


def test_magistrate_change_that_echoes_is_unapplied(monkeypatch):
    _corpus(monkeypatch)
    quote = "Take that with a big grain of salt."
    fix = "I wouldn't lock onto any one number, the timing window shifts."
    text = f"Morning, its Friday.\n\n{quote}\n\nDid you pull the boat?"
    ruling = {"required_changes": [f"{quote} -> {fix}"]}
    issues, unapplied = RP._magistrate_fixes(ruling, text,
                                             recent_bodies=[YESTERDAY])
    assert issues == []
    assert len(unapplied) == 1
    assert "lock onto any one" in unapplied[0]["why"]


def test_no_history_or_thin_corpus_never_refuses(monkeypatch):
    _corpus(monkeypatch)
    assert RP._echoes_recent(ECHO_FIX, []) is None
    assert RP._echoes_recent(ECHO_FIX, None) is None
    # A fresh install: fewer than three posts to judge rarity against.
    _corpus(monkeypatch, df={"lock": 1, "onto": 1}, n=2)
    assert RP._echoes_recent(ECHO_FIX, [YESTERDAY]) is None
