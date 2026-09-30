"""A reviewer may not prescribe what the deterministic gate forbids.

WHAT THIS IS FOR. 2026-09-30, and it cost the day. The brief said Wolf Creek
"gusts to 50". The writer wrote "gusts 40-60" -- a range that CONTAINS the
brief's figure, which is what SHARED_RULES rule 1 asks for and what the gate
passes. The fact checker called that critical and supplied, as its remedy, the
literal string "gusts to 50": the point-value gust guardrails has blocked since
the hand-edit era. The magistrate required it, the final-round auto-patch
spliced it in, and the gate blocked the patched text. Round 2 died the same
way. Nothing published.

The fix screens every proposed replacement through the gate BEFORE the
magistrate reads the reports. The objection survives; the remedy does not.

THE EIGHT CASES:
  1. the 09-30 gust remedy is withheld, and only that one
  2. the objection itself survives the withheld remedy
  3. round 1 repeats it on a draft the gate ALREADY blocks (the delta rule):
     the road hedge that CURES the block is kept, the gust remedy still refused
  4. the magistrate's prompt never carries the forbidden sentence
  5. the magistrate cannot require what the gate forbids either
  6. with the screen, the final-round patch leaves the gate PASSing
  7. without the screen, that same patch still BLOCKS (the recorded outcome)
  8. the transcript says what was withheld and why

Every draft, report and ruling below is verbatim from
state/panel/2026-09-30-school_call.md.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))

from test_panel_0927_regression import Script  # noqa: E402
from test_runners import _fakes                # noqa: E402
from wx import bundle as B                     # noqa: E402
from wx import guardrails as G                 # noqa: E402
from wx import review_panel as RP              # noqa: E402

GUST_BLOCK = "point-value gust"

# --- the drafts, verbatim -------------------------------------------------------
DRAFT_R1 = """09/30/26 5:47am: Morning, its Wednesday. Sky's still overcast here and the air's got that heavy feel to it, which is what the bus run's dealing with this morning.

We're under a Flood Watch from the Grand Junction office, and its split by zone. Vallecito and up the Florida (COZ019) stay in it through Thursday morning. Durango and Bayfield (COZ022) drop out at 6am today. The ground's already saturated from the last couple weeks and more rain's coming, so flash flooding and rises on local rivers are the concern. The full product's at weather.gov/gjt.

Rain everywhere today, including up high. The snow line's well above the passes, above the Weminuche, above every road and trail anyone's on, so its all liquid and the totals are what matter.

Durango and the Animas Valley (6,500') should see another inch or so through the day, heaviest 6am-noon with a half-inch in that window. Gusts stay light, under 10mph. I'd expect wet pavement for the morning commute and through the afternoon.

Bayfield and up the Pine (6,900') are in the same setup, looking at an inch total with the heaviest band 6am-noon. The 501 should be wet for the bus run and stay that way most of the day.

Vallecito and the Florida (7,650') are where the models split hard. The Euro's cranking out nearly an inch today, the GFS and GEM are down around a quarter-inch, and ICON's in the middle at 0.64". Take that with a big grain of salt (the spread's almost three-quarters of an inch and we wont know which one's right until its over). The 240 should be wet this morning either way. Gusts 10-15 through the day.

The high Weminuche (10,500'+) stays rain too, looking at a half-inch or more with gusts 15-30.

The passes should stay rain at pass level. Coal Bank, Molas and Red Mountain all get wet pavement through the day. Wolf Creek might see a dusting up top but nothing that sticks. For current closures and chain law: cotrip.org

Districts decide by 6:30. Thursday's dry and warmer, clearing out behind this system.

What'd the 501 or the 240 look like on your drive in?"""

DRAFT_R3 = """09/30/26 5:47am: Morning, its Wednesday. Sky's still overcast here and the air's got that heavy feel to it this morning.

We're under a Flood Watch from the Grand Junction office, and its split by zone. Vallecito and up the Florida (COZ019) stay in it through 5pm today. Durango and Bayfield (COZ022) drop out at 6am today. The ground's already saturated from the last couple weeks and more rain's coming, so flash flooding and rises on local rivers are the concern. The full product's at weather.gov/gjt.

Rain everywhere today, including up high. The snow line's well above the passes, above the Weminuche, above every road and trail anyone's on, so its all liquid and the totals are what matter.

Durango and the Animas Valley (6,500') should see another inch or so through the day, heaviest 6am-noon with a half-inch in that window. Gusts stay light, under 10mph. I'd expect wet pavement for the morning commute and through the afternoon.

Bayfield and up the Pine (6,900') are in the same setup, looking at an inch total with the heaviest band 6am-noon. The 501 should be wet for the bus run and stay that way most of the day.

Vallecito and the Florida (7,650') are where the models split hard. The Euro's cranking out nearly an inch today, the GFS and GEM are down around a quarter-inch, and ICON's in the middle at 0.64". Take that with a big grain of salt (the spread's almost three-quarters of an inch and we wont know which one's right until its over). The 240 should be wet this morning either way. Gusts 10-15 through the day.

The high Weminuche (10,500'+) stays rain too, looking at a half-inch or more with gusts 15-30.

The passes should stay rain at pass level. Coal Bank, Molas and Red Mountain should see wet pavement through the day. Wolf Creek could see a couple inches up top with gusts 40-60. For current closures and chain law: cotrip.org

Districts decide by 6:30. Thursday's dry and warmer, clearing out behind this system.

What's your gauge showing this morning compared to yesterday?"""

# --- round 3, the sentences the panel argued about ------------------------------
WATCH_R3 = "Vallecito and up the Florida (COZ019) stay in it through 5pm today."
WATCH_FIX = ("Vallecito and up the Florida (COZ019) stay in it through 5pm. "
             "Durango and Bayfield (COZ022) drop out at 6am.")
DURANGO_R3 = ("Durango and the Animas Valley (6,500') should see another inch or so "
              "through the day, heaviest 6am-noon with a half-inch in that window.")
DURANGO_FIX = ("Durango and the Animas Valley (6,500') should see close to an inch "
               "and a tenth through the day, heaviest 6am-noon with about a "
               "half-inch in that window.")
BAYFIELD_R3 = ("Bayfield and up the Pine (6,900') are in the same setup, looking at "
               "an inch total with the heaviest band 6am-noon.")
BAYFIELD_FIX = ("Bayfield and up the Pine (6,900') are in the same setup, looking at "
                "right around an inch total with the heaviest band 6am-noon.")
WOLF_R3 = "Wolf Creek could see a couple inches up top with gusts 40-60."
WOLF_FIX = "Wolf Creek could see a couple inches up top with gusts to 50."   # BLOCKED
GAUGE_R3 = "What's your gauge showing this morning compared to yesterday?"
OPENER_R3 = ("Morning, its Wednesday. Sky's still overcast here and the air's got "
             "that heavy feel to it this morning.")
OPENER_FIX = ("Morning, its Wednesday. The woodpile's still damp from overnight and "
              "the overcast hasn't broken yet.")
CLOSER_FIX = "How's the 240 holding up on your end this morning?"

for _s in (WATCH_R3, DURANGO_R3, BAYFIELD_R3, WOLF_R3, GAUGE_R3, OPENER_R3):
    assert _s in DRAFT_R3, _s

# --- round 1, the sentences the panel argued about ------------------------------
ROAD_R1 = "Coal Bank, Molas and Red Mountain all get wet pavement through the day."
ROAD_FIX = "Coal Bank, Molas and Red Mountain should see wet pavement through the day."
WOLF_R1 = "Wolf Creek might see a dusting up top but nothing that sticks."
WATCH_R1 = "Vallecito and up the Florida (COZ019) stay in it through Thursday morning."

for _s in (ROAD_R1, WOLF_R1, WATCH_R1):
    assert _s in DRAFT_R1, _s


def facts_r3():
    """The round 3 fact check, verbatim. Fresh each call: screen_fixes mutates."""
    return {"verdict": "issues", "issues": [
        {"severity": "critical", "quote": WATCH_R3,
         "problem": "The Flood Watch for COZ019 expires at 5:00PM MDT (17:00), not 5pm.",
         "evidence": "Flood Watch (COZ019) ... expires 2026-09-30T17:00:00-06:00",
         "fix": WATCH_FIX},
        {"severity": "critical", "quote": DURANGO_R3,
         "problem": 'the 48h total is 1.11in, not "an inch or so".',
         "evidence": ("Durango and the Animas Valley (6500 ft, zone COZ022): "
                      "next 48h totals: 0.0in snow, 1.11in liquid"),
         "fix": DURANGO_FIX},
        {"severity": "critical", "quote": BAYFIELD_R3,
         "problem": 'The 48h total for Bayfield is 0.99in, not "an inch".',
         "evidence": ("Bayfield and up the Pine (6900 ft, zone COZ022): "
                      "next 48h totals: 0.0in snow, 0.99in liquid"),
         "fix": BAYFIELD_FIX},
        {"severity": "critical", "quote": WOLF_R3,
         "problem": "The brief shows Wolf Creek Pass gusts to 50, not 40-60.",
         "evidence": ("US-160 east, Wolf Creek Pass, 10,857 ft: a couple inches at "
                      "most, gusts to 50."),
         "fix": WOLF_FIX},
        {"severity": "critical", "quote": GAUGE_R3,
         "problem": ("The brief says NO READING TODAY, so the closing question "
                     "cannot ask about gauge measurements."),
         "evidence": "YOUR OWN GAUGE AND STAKE: NO READING TODAY.", "fix": ""},
    ]}


def editor_r3():
    """The round 3 editor report, verbatim."""
    return {"verdict": "issues", "issues": [
        {"severity": "minor", "quote": OPENER_R3,
         "problem": "The opener reuses the construction of 2026-09-18.",
         "evidence": "PERSONA", "fix": OPENER_FIX},
        {"severity": "minor", "quote": GAUGE_R3,
         "problem": "The closing question reuses recent gauge questions.",
         "evidence": "PERSONA", "fix": CLOSER_FIX},
    ]}


def facts_r1():
    """The round 1 fact check, verbatim, minus the downgraded Weminuche minor."""
    return {"verdict": "issues", "issues": [
        {"severity": "critical", "quote": WATCH_R1,
         "problem": "The Flood Watch for COZ019 expires Wednesday at 5:00PM.",
         "evidence": "Flood Watch (COZ019) ... expires 2026-09-30T17:00:00-06:00",
         "fix": "Vallecito and up the Florida (COZ019) stay in it through 5pm today."},
        {"severity": "critical", "quote": WOLF_R1,
         "problem": 'The brief says Wolf Creek gets "a couple inches at most".',
         "evidence": ("US-160 east, Wolf Creek Pass, 10,857 ft: a couple inches at "
                      "most, gusts to 50."),
         "fix": WOLF_FIX},
    ]}


def editor_r1():
    """The round 1 editor report: the road sentence the gate had just blocked."""
    return {"verdict": "issues", "issues": [
        {"severity": "critical", "quote": ROAD_R1,
         "problem": ("States a present-tense road surface condition; the automated "
                     "gate already flagged this exact sentence as BLOCK."),
         "evidence": "AUTOMATED RULE GATE, ALREADY RUN ON THIS DRAFT: BLOCK",
         "fix": ROAD_FIX},
    ]}


# The magistrate's round 3 ruling, verbatim: five required changes, the third
# of which is the sentence the gate forbids.
RULING_R3 = {
    "ruling": "revise", "title": "", "dismissed": [],
    "rationale": ("Five required changes: three numbers outside their brief "
                  "ranges, one gauge question forbidden by NO READING TODAY, "
                  "and one opener that reuses the 2026-09-18 construction."),
    "required_changes": [
        '"' + DURANGO_R3 + '" -> "' + DURANGO_FIX + '"',
        '"' + BAYFIELD_R3 + '" -> "' + BAYFIELD_FIX + '"',
        '"' + WOLF_R3 + '" -> "' + WOLF_FIX + '"',
        '"' + GAUGE_R3 + '" -> "' + CLOSER_FIX + '"',
        '"' + OPENER_R3 + '" -> "' + OPENER_FIX + '"',
    ]}


def bundle():
    return B.build(fetchers=_fakes())


# --- 1 --------------------------------------------------------------------------

def test_the_0930_gust_remedy_is_withheld_and_only_that_one():
    """The gate passes the round 3 draft. Three of the fact checker's four
    replacements leave it passing; the fourth is "gusts to 50"."""
    bun, facts = bundle(), facts_r3()
    assert RP._gate_flags(bun, DRAFT_R3, False)[0] == G.PASS

    refused = RP.screen_fixes(bun, DRAFT_R3, facts, "fact checker")

    assert [r["quote"] for r in refused] == [WOLF_R3]
    assert refused[0]["fix"] == WOLF_FIX
    assert refused[0]["who"] == "fact checker"
    assert GUST_BLOCK in refused[0]["why"]
    # the other three are untouched, word for word
    kept = {i["quote"]: i["fix"] for i in facts["issues"]}
    assert kept[WATCH_R3] == WATCH_FIX
    assert kept[DURANGO_R3] == DURANGO_FIX
    assert kept[BAYFIELD_R3] == BAYFIELD_FIX
    # and the editor's two, screened separately, both survive
    ed = editor_r3()
    assert RP.screen_fixes(bun, DRAFT_R3, ed, "editor") == []
    assert [i["fix"] for i in ed["issues"]] == [OPENER_FIX, CLOSER_FIX]


# --- 2 --------------------------------------------------------------------------

def test_the_objection_survives_the_withheld_remedy():
    """"gusts 40-60" really was outside the brief. Dropping the objection with
    the bad remedy would trade one failure for a worse one, so only the fix
    goes: the issue keeps its severity, its quote and its evidence, and the
    problem now says a replacement was withheld and why."""
    facts = facts_r3()
    RP.screen_fixes(bundle(), DRAFT_R3, facts, "fact checker")
    wolf = next(i for i in facts["issues"] if i["quote"] == WOLF_R3)

    assert wolf["fix"] == "", "the forbidden replacement must not survive"
    assert wolf["severity"] == "critical", "the objection is untouched"
    assert "gusts to 50" in wolf["evidence"], "the brief line it rests on stays"
    assert wolf["refused_fix"] == WOLF_FIX and GUST_BLOCK in wolf["refused_why"]
    assert "withheld" in wolf["problem"] and GUST_BLOCK in wolf["problem"]
    assert wolf["problem"].startswith("The brief shows Wolf Creek Pass gusts to 50")


# --- 3 --------------------------------------------------------------------------

def test_round_1_repeats_it_on_a_draft_the_gate_already_blocks():
    """The delta rule. Round 1 is BLOCK already, for the road sentence. A
    screen that asked "does the patched text pass?" would refuse every
    replacement on this draft, including the one that CURES the block."""
    bun = bundle()
    verdict, reasons = RP._gate_flags(bun, DRAFT_R1, False)
    assert verdict == G.BLOCK and "road surface" in reasons[0]

    facts, editor = facts_r1(), editor_r1()
    refused = (RP.screen_fixes(bun, DRAFT_R1, facts, "fact checker")
               + RP.screen_fixes(bun, DRAFT_R1, editor, "editor"))

    # The gust remedy is caught even though the verdict was BLOCK before and
    # stays BLOCK after: it adds a reason of its own.
    assert [r["quote"] for r in refused] == [WOLF_R1]
    assert GUST_BLOCK in refused[0]["why"]
    # The editor's hedge, which takes the draft from BLOCK to PASS, is kept.
    assert editor["issues"][0]["fix"] == ROAD_FIX
    assert RP._gate_flags(bun, DRAFT_R1.replace(ROAD_R1, ROAD_FIX), False)[0] == G.PASS
    # And so is the Flood Watch correction, which has nothing to do with either.
    assert facts["issues"][0]["fix"].endswith("through 5pm today.")


# --- 4 --------------------------------------------------------------------------

def test_the_magistrate_prompt_never_carries_the_forbidden_sentence():
    """The whole point of screening BEFORE the ruling: the magistrate cannot
    require a sentence it was never shown."""
    facts, editor = facts_r3(), editor_r3()
    RP.screen_fixes(bundle(), DRAFT_R3, facts, "fact checker")
    seen = {}

    def fake_llm(msgs):
        seen["user"] = msgs[-1]["content"]
        return json.dumps({"ruling": "revise", "required_changes": []})

    RP.rule(fake_llm, "BRIEF", DRAFT_R3, facts, editor, G.PASS, [], 3, 3)

    prompt = seen["user"]
    report = prompt.split("FACT CHECK REPORT:")[1]
    # The brief line really does read "gusts to 50" and the magistrate has to
    # see that evidence. What it must never see is that sentence OFFERED as a
    # remedy: _fmt_report writes a remedy, and only a remedy, as "-> <sentence>".
    assert "-> " + WOLF_FIX not in prompt, \
        "the magistrate was handed the sentence the gate forbids"
    assert not [ln for ln in report.splitlines() if ln.rstrip().endswith(WOLF_FIX)]
    # but it is told there is a problem, and that a remedy was withheld
    assert WOLF_R3 in prompt
    assert "not 40-60" in prompt and "withheld" in prompt and GUST_BLOCK in prompt
    # the replacements that passed the screen are still offered
    assert DURANGO_FIX in prompt and OPENER_FIX in prompt


# --- 5 --------------------------------------------------------------------------

def test_the_magistrate_cannot_require_what_the_gate_forbids_either():
    """Belt and braces. The reviewers are screened first, but the magistrate
    writes its own sentences too, and a required change is spliced in
    literally. Replayed against the ruling it actually wrote on 09-30."""
    bun = bundle()

    def gate(q, f):
        return RP._fix_breaks_gate(bun, DRAFT_R3, q, f)

    fixes, unapplied = RP._magistrate_fixes(RULING_R3, DRAFT_R3, gate=gate)

    assert [u["quote"] for u in unapplied] == [WOLF_R3]
    assert "rule gate refuses" in unapplied[0]["why"]
    assert GUST_BLOCK in unapplied[0]["why"]
    assert [f["quote"] for f in fixes] == [DURANGO_R3, BAYFIELD_R3, GAUGE_R3, OPENER_R3]

    # Without the gate argument the old behaviour is unchanged: all five pass
    # the word list and the shape test, which is how 09-30 happened.
    fixes_no_gate, unapplied_no_gate = RP._magistrate_fixes(RULING_R3, DRAFT_R3)
    assert unapplied_no_gate == [] and len(fixes_no_gate) == 5


# --- 6 --------------------------------------------------------------------------

def test_with_the_screen_the_final_round_patch_leaves_the_gate_passing():
    """The 09-30 final round, replayed with the screen in front of it."""
    bun, facts, editor = bundle(), facts_r3(), editor_r3()
    RP.screen_fixes(bun, DRAFT_R3, facts, "fact checker")
    RP.screen_fixes(bun, DRAFT_R3, editor, "editor")

    def gate(q, f):
        return RP._fix_breaks_gate(bun, DRAFT_R3, q, f)

    mag_fixes, unapplied = RP._magistrate_fixes(RULING_R3, DRAFT_R3, gate=gate)

    patched, applied, _ = RP._apply_fixes(
        DRAFT_R3, (("fact checker", facts), ("editor", editor),
                   ("magistrate", {"issues": mag_fixes, "overrides": True})))

    assert "gusts to 50" not in patched
    assert WOLF_R3 in patched, "the sentence stands, unfixed, rather than blocked"
    assert RP._gate_flags(bun, patched, False) == (G.PASS, [])
    # the corrections that were safe all landed
    assert DURANGO_FIX in patched and BAYFIELD_FIX in patched
    assert OPENER_FIX in patched and CLOSER_FIX in patched
    assert WOLF_R3 not in [a["quote"] for a in applied]
    # and the post is still HELD, because the Wolf Creek objection now stands
    # with no remedy: silence is recoverable, a wrong gust figure is not.
    assert [u["quote"] for u in unapplied if u["quote"] in patched] == [WOLF_R3]
    assert WOLF_R3 in [i["quote"] for i in RP._blocking_fact_issues(facts, patched)]


# --- 7 --------------------------------------------------------------------------

def test_without_the_screen_the_same_patch_still_blocks():
    """The control, and the recorded outcome. Without the screen this is what
    state/panel/2026-09-30-school_call.md shows: "Rule gate on the patched
    text: block -- draft gives a point-value gust ('gusts to 50')"."""
    bun, facts, editor = bundle(), facts_r3(), editor_r3()
    mag_fixes, unapplied = RP._magistrate_fixes(RULING_R3, DRAFT_R3)
    assert unapplied == []

    patched, applied, _ = RP._apply_fixes(
        DRAFT_R3, (("fact checker", facts), ("editor", editor),
                   ("magistrate", {"issues": mag_fixes, "overrides": True})))

    assert "Wolf Creek could see a couple inches up top with gusts to 50." in patched
    verdict, reasons = RP._gate_flags(bun, patched, False)
    assert verdict == G.BLOCK
    assert any(GUST_BLOCK in r for r in reasons), reasons
    assert len(applied) == 6


# --- 8 --------------------------------------------------------------------------

def test_the_transcript_records_what_was_withheld_and_why():
    """Through the loop, and auditable afterwards. The transcript is committed
    so the reasoning can be read back; a remedy that was silently dropped is
    not a reasoning anyone can read."""
    bun = bundle()
    script = Script(RULING_R3, facts=[facts_r3()], editor=editor_r3())
    out = RP.run_panel(bun, DRAFT_R3, slot="school_call", writer_llm=script,
                       rounds=1, log=lambda *_: None)

    screened = out["rounds"][-1]["screened"]
    assert [s["quote"] for s in screened] == [WOLF_R3]
    assert screened[0]["fix"] == WOLF_FIX
    assert out["approved"] is False, "the Wolf Creek objection stands unremedied"
    assert "gusts to 50" not in out["text"]

    t = RP.transcript(out, bun, "school_call")
    assert "Replacements withheld before the magistrate saw them" in t
    assert WOLF_FIX in t and GUST_BLOCK in t
    # and the patched text the panel produced never carried it
    assert "Rule gate on the patched text: block" not in t
