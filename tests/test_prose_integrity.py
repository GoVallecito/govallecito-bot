"""The splice guard, the prose gate and the morning track record.

WHAT THIS IS FOR. On 2026-10-03 the website published

    "Morning, its Saturday. Saturday, and the air's got that October bite..."
    "...over the high country by afternoon., with just a slight chance of an
     isolated afternoon shower over the high terrain."

Both came out of the final-round auto-patch: the editor quoted a FRAGMENT of
a sentence and its replacement ended in a full stop, so the tail of the
original survived the period. Nothing in the rule gate asked whether the
result was English.

The payloads below are the real transcript values from
state/panel/2026-10-03-school_call.md.
"""
import datetime as _dt
import glob
import json
import os
import sys

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(REPO, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_runners import _fakes                # noqa: E402
from wx import bundle as B                     # noqa: E402
from wx import compose as CO                   # noqa: E402
from wx import constants as C                  # noqa: E402
from wx import guardrails as G                 # noqa: E402
from wx import review_panel as RP              # noqa: E402
from wx import verify as V                     # noqa: E402

OCT3 = (
    "10/03/26 5:45am: Morning, its Saturday. The sky's clear out the kitchen "
    "window.\n\n"
    "Durango and the Animas Valley (6,500') should see dry conditions all day.\n\n"
    "Tomorrow looks like a repeat, warm, mostly dry, with just a slight chance "
    "of an isolated afternoon shower over the high terrain.\n\n"
    "Anybody heading up into the Weminuche?"
)

EDITOR_FRAGMENT = {"verdict": "issues", "issues": [{
    "severity": "minor",
    "quote": "Tomorrow looks like a repeat, warm, mostly dry",
    "problem": "flat opener for the outlook",
    "evidence": "PERSONA",
    "fix": "Sunday's the same setup, just a tick warmer with that slight "
           "chance of a shower over the high country by afternoon.",
}]}

MAGISTRATE_WHOLE = {"overrides": True, "issues": [{
    "severity": "major",
    "quote": "Tomorrow looks like a repeat, warm, mostly dry, with just a "
             "slight chance of an isolated afternoon shower over the high terrain.",
    "problem": "name the day",
    "evidence": "PERSONA",
    "fix": "Sunday's the same setup, just a tick warmer, with a slight chance "
           "of an isolated afternoon shower over the high terrain.",
}]}

# What the website actually carried on the morning of 2026-10-03.
PUBLISHED = (
    "10/03/26 5:45am: Morning, its Saturday. Saturday, and the air's got that "
    "October bite when you step outside.\n\n"
    "Durango and the Animas Valley (6,500') dry all day, warming from the "
    "upper 40s this morning into the upper 70s this afternoon.\n\n"
    "Sunday's the same setup, just a tick warmer with that slight chance of a "
    "shower over the high country by afternoon., with just a slight chance of "
    "an isolated afternoon shower over the high terrain.\n\n"
    "Anybody heading up into the Weminuche or are the trails getting too "
    "chewed up?"
)

# 2026-09-25, the passes paragraph, verbatim from state/drafts.
SEP25_PASSES = (
    "Snow line's higher today than anywhere anybody here goes. All rain "
    "everywhere, including up high in the Weminuche where it stays in the low "
    "40s. Coal Bank and Molas should stay rain at pass level through the "
    "morning with a couple inches at most possible by tonight, but that's "
    "this afternoon's story, not this morning's. Red Mountain's the same "
    "setup. Wolf Creek should see a couple inches at most by tonight, same "
    "window."
)

BROKEN_SEAM = "by afternoon., with just a slight chance"


# --- the splice guard --------------------------------------------------------

def test_the_1003_fragment_fix_is_dropped_not_spliced():
    patched, applied, skipped, unsafe = RP._apply_fixes(
        OCT3, (("editor", EDITOR_FRAGMENT),))

    assert applied == []
    assert len(unsafe) == 1 and unsafe[0]["who"] == "editor"
    assert patched == OCT3
    assert BROKEN_SEAM not in patched


def test_dropping_the_fragment_lets_the_magistrates_whole_sentence_fix_land():
    """The key one: the guard is why the intended edit now applies."""
    patched, applied, skipped, unsafe = RP._apply_fixes(
        OCT3, (("editor", EDITOR_FRAGMENT), ("magistrate", MAGISTRATE_WHOLE)))

    assert len(unsafe) == 1
    assert [a["who"] for a in applied] == ["magistrate"]
    assert skipped == []
    assert MAGISTRATE_WHOLE["issues"][0]["fix"] in patched
    assert BROKEN_SEAM not in patched
    assert G.prose_damage(patched) == []


def test_a_whole_sentence_replacement_still_applies():
    text = "The 160 looks fine. The passes are dry. Check cotrip.org before you go."
    patched, applied, skipped, unsafe = RP._apply_fixes(text, (("editor", [{
        "severity": "major", "quote": "The passes are dry.",
        "fix": "The passes should stay dry."}]),))

    assert unsafe == [] and skipped == []
    assert len(applied) == 1
    assert "The passes should stay dry. Check cotrip.org" in patched


def test_a_mid_clause_fix_with_no_terminal_punctuation_still_applies():
    text = "Wind picks up after lunch. Gusts to 20mph this afternoon, easing by dark."
    patched, applied, skipped, unsafe = RP._apply_fixes(text, (("fact checker", [{
        "severity": "major", "quote": "Gusts to 20mph", "fix": "Gusts 15-25"}]),))

    assert unsafe == [] and skipped == []
    assert len(applied) == 1
    assert "Gusts 15-25 this afternoon, easing by dark." in patched


# --- the prose gate ----------------------------------------------------------

def test_prose_damage_names_both_symptoms_in_what_published():
    symptoms = [s for s, _ in G.prose_damage(PUBLISHED)]

    assert "a word repeated back to back" in symptoms
    assert "a sentence ends and then continues with a comma" in symptoms


def test_the_gate_blocks_what_published_as_malformed():
    verdict, reasons = G.evaluate(B.build(fetchers=_fakes()), PUBLISHED)

    assert verdict == G.BLOCK
    assert any("malformed" in r for r in reasons), reasons


def test_nothing_on_the_site_or_held_for_it_trips_the_prose_gate():
    weather = os.path.join(REPO, "site", "weather")
    files = sorted(glob.glob(os.path.join(weather, "*.md"))
                   + glob.glob(os.path.join(weather, "_pending", "*.md")))
    assert len(files) >= 10, f"only {len(files)} posts found, the sweep is vacuous"

    flagged = {}
    for path in files:
        with open(path, encoding="utf-8") as f:
            damage = G.prose_damage(f.read())
        if damage:
            flagged[os.path.basename(path)] = damage
    assert flagged == {}


def test_the_0925_repetition_is_reported_and_never_blocks():
    assert G.duplicated_phrase(SEP25_PASSES) == "a couple inches at most"
    assert G.prose_damage(SEP25_PASSES) == []


# --- the track record --------------------------------------------------------

def _scored(missed):
    bands = [{"band": "vallecito", "called_in": [0.0, 0.5],
              "observed_in": 0.9 if missed else 0.2,
              "in_range": not missed,
              "direction": "under-forecast" if missed else "in range"}]
    return {"valid_date": "2026-10-02", "age_days": 1, "bands": bands,
            "bands_in_range": 0 if missed else 1, "bands_scored": 1,
            "missed": [b for b in bands if b["in_range"] is False],
            "snow_line_error_ft": None}


def test_the_brief_carries_a_missed_band_and_asks_for_the_mechanism():
    brief = CO.render_bundle({"verified_yesterday": _scored(missed=True)})

    assert "YOUR LAST FORECAST, SCORED (valid 2026-10-02, 1 day(s) ago)" in brief
    assert "you called 0.0-0.5in, it came in 0.9in, under" in brief
    assert "0 of 1 bands in range" in brief
    assert "You MISSED a band" in brief
    assert "physical mechanism" in brief
    assert "say NOTHING about it" not in brief


def test_a_clean_score_tells_the_writer_to_say_nothing():
    brief = CO.render_bundle({"verified_yesterday": _scored(missed=False)})

    assert "YOUR LAST FORECAST, SCORED" in brief
    assert "say NOTHING about it" in brief
    assert "You MISSED a band" not in brief


def test_no_score_states_the_absence_out_loud():
    for bundle in ({}, {"verified_yesterday": None}):
        brief = CO.render_bundle(bundle)
        assert "YOUR LAST FORECAST, SCORED: NOTHING SCORED YET" in brief
        assert "invented" in brief
        assert "You MISSED a band" not in brief


def test_last_scored_reads_the_log_and_keeps_a_stale_score_out(tmp_path, monkeypatch):
    yesterday = (C.local_date() - _dt.timedelta(days=1)).isoformat()
    log = tmp_path / "forecast_log.json"
    log.write_text(json.dumps({"forecasts": [{
        "id": f"{yesterday}-0", "valid_date": yesterday, "verified": True,
        "score": {"bands_scored": 1, "bands_in_range": 0, "snow_line_error_ft": None,
                  "per_band": {"vallecito": {
                      "predicted_range_in": [0.0, 0.5], "observed_in": 0.9,
                      "in_range": False, "miss_in": 0.4,
                      "direction": "under-forecast"}}},
    }]}), encoding="utf-8")
    monkeypatch.setattr(V, "FORECAST_LOG", str(log))

    got = V.last_scored()
    assert got["valid_date"] == yesterday and got["age_days"] == 1
    assert [b["band"] for b in got["missed"]] == ["vallecito"]
    assert got["bands"][0]["called_in"] == [0.0, 0.5]

    assert V.last_scored(limit_days=0) is None
