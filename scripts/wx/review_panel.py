"""
The review panel: two reviewers and a magistrate, in a loop, before anything
reaches the website.

WHY THIS EXISTS
Every draft from 09-09 to 09-19 was held for a human, and nearly every one
needed the same kinds of hand edits: a gust given as a point value, a road
stated in the present tense, a personal detail with an invented number behind
it, an opener recycled from yesterday, a model that does not exist. The
deterministic guardrails catch the patterns someone has already written a
regex for. This catches the rest, the way the human review did, without the
human.

THE LOOP (one "round")
  1. FACT CHECKER reads the exact data brief the writer saw and the draft, and
     lists every claim the data does not support.
  2. EDITOR reads the persona rules and the recent posts, and lists every
     break in voice, format, repetition or local accuracy.
  3. MAGISTRATE reads both reports, the draft, the brief, and anything the
     deterministic gate flagged, and rules: APPROVE, REVISE, or REJECT. It may
     overrule a reviewer, and must say why when it does.
  4. On REVISE the writer revises against the magistrate's required changes
     only, the deterministic gate re-checks the revision, and the next round
     starts with fresh reviews of the new text.

Nothing publishes unless the magistrate says APPROVE on the exact text that is
published. A REJECT, or no approval after the last round, falls back to the old
behaviour: stage it and open a review issue. Silence is recoverable; a wrong
forecast at 5:45am is not.

Every call is an injected callable(messages) -> str, the same contract as
compose.compose, so the whole loop is testable offline.
"""

import json
import os
import re

from . import compose as CO
from . import guardrails as G
from . import sanitize as SAN

APPROVE, REVISE, REJECT = "approve", "revise", "reject"

DEFAULT_MAX_ROUNDS = 3


def max_rounds():
    try:
        return max(1, int(os.environ.get("WX_PANEL_MAX_ROUNDS") or DEFAULT_MAX_ROUNDS))
    except ValueError:
        return DEFAULT_MAX_ROUNDS


def enabled():
    return (os.environ.get("WX_REVIEW_PANEL") or "true").strip().lower() \
        not in ("false", "0", "no", "off")


# --- prompts ----------------------------------------------------------------

_REPORT_SHAPE = """Reply with ONE JSON object and nothing else:
{
  "verdict": "clean" or "issues",
  "issues": [
    {"severity": "critical" | "major" | "minor",
     "quote": "<the exact sentence from the draft>",
     "problem": "<what is wrong, one sentence>",
     "fix": "<the replacement sentence, written in the forecaster's voice>"}
  ]
}
Severity: critical = wrong or unsupported fact a reader could act on (a
temperature, timing, precipitation, alert, road or pass claim, snow line,
weekday), or anything unsafe. major = breaks a hard rule of the persona
(repetition, present-tense road state, point values, bold/headers, invented
personal measurement, bare percentage, wrong local name) or reads clearly as a
bot. minor = polish. Quote exactly. If nothing is wrong, return
{"verdict": "clean", "issues": []}. Do not invent problems to look thorough."""

FACT_CHECKER_SYSTEM = """You are the fact checker for a hyperlocal weather page \
covering Vallecito, Bayfield and Durango, Colorado (La Plata County). You check \
one draft post against the data brief the writer was given. The brief is the \
only truth: anything in the draft the brief does not support is a problem, even \
if it is probably true in the real world.

Check every claim, one by one:
- Every temperature, wind, gust, precipitation amount, timing window and snow \
line against the brief, band by band (Durango/Animas Valley 6,500 ft, Bayfield/\
Pine 6,900 ft, Vallecito/Florida 7,650 ft, high Weminuche 10,000 ft+).
- The date stamp and weekday match the brief.
- Every NWS alert named exists in the brief with that exact product name \
(a Flood Watch is not a Flash Flood Watch).
- Every model named (Euro, GFS, ICON, GEM, ...) is in the brief, and what the \
draft says each model shows matches the brief.
- SNOTEL, streamflow, reservoir and basin numbers match the brief exactly.
- Any gauge or snow stake number is backed by the brief's home gauge block. If \
the brief says NO READING TODAY, any gauge/stake figure is critical.
- No road, pass or closure is stated as a present fact unless the brief carries \
CDOT data for it.
- No claim about the past (earlier this week, last night, this summer) the brief \
does not contain.
- No snow line figure above the terrain (the brief says when it is all rain to \
the summits).
""" + "\n" + _REPORT_SHAPE

EDITOR_SYSTEM = """You are the editor for a hyperlocal weather page covering \
Vallecito, Bayfield and Durango, Colorado. The forecaster's full persona and \
rulebook follows between the markers. Your job is to judge one draft against \
that rulebook and against the forecaster's recent posts: voice, tone, format, \
structure, repetition, local accuracy (place names, roads, elevations, local \
terms), and whether a local reading it at 6am on a phone gets what they need \
fast. You are not the fact checker; leave the numbers to them unless a number \
breaks a style rule (point values, bare percentages).

Check hardest, because these keep shipping:
- The opener, the pivot near the end, and the closing question must not reuse \
the construction of any recent post, even with nouns swapped.
- Exactly one personal detail, and it must not contain a measurement unless the \
brief supports one.
- Roads and passes only in future or conditional tense.
- Ranges, not point values, for gusts and amounts.
- No bold, no headers, no bullet lists, no em dashes, no hashtags, no emoji.
- The zones walk in order with elevations.
- Rotated hedging: not the same grain-of-salt phrasing as recent posts.

=== PERSONA RULEBOOK START ===
{persona}
=== PERSONA RULEBOOK END ===
""" + "\n" + _REPORT_SHAPE

MAGISTRATE_SYSTEM = """You are the magistrate: the final authority on whether \
one weather post for a small mountain community (Vallecito, Bayfield, Durango, \
Colorado) is published to the website. Nothing publishes without your approval, \
and there is no human after you. People make school-run, pass-driving, \
livestock and camping decisions on this post.

You receive the data brief, the draft, a fact-check report, an editor report, \
and any flags from the automated rule gate. Rule on the draft AS WRITTEN.

- APPROVE only if you would stake the page's reputation on it: no critical or \
major issue stands, every fact is supported by the brief, and it reads like the \
forecaster, not a bot. Minor polish alone never blocks approval.
- REVISE when fixable problems stand. List each required change precisely: \
quote the sentence and give the replacement or the exact instruction. Do not \
ask for changes you would not block on.
- REJECT only when the draft cannot be fixed by editing (the data itself is \
contradictory or unsafe to publish on).
- You may overrule a reviewer. When you dismiss a reviewer's critical or major \
issue, say why in "dismissed". A reviewer that is wrong about the brief is \
wrong; check the brief yourself.
- Anything the automated gate flagged must be either fixed or explicitly \
judged acceptable in your rationale.

Reply with ONE JSON object and nothing else:
{
  "ruling": "approve" | "revise" | "reject",
  "required_changes": ["<quote> -> <replacement or instruction>", ...],
  "dismissed": ["<reviewer issue you overruled, and why>", ...],
  "title": "<on approve: a 2-6 word headline for the post, plain words, no \
snow line figure, no colon, no emoji; otherwise empty>",
  "rationale": "<two or three sentences>"
}"""

REVISER_INSTRUCTION = """THE REVIEW MAGISTRATE SENT YOUR DRAFT BACK. Revise it.

Make every required change below. Change nothing else: keep the forecast, the \
numbers the brief supports, the structure and the voice. Do not add new facts. \
Return only the post, starting with the date stamp.

YOUR CURRENT DRAFT:
{draft}

REQUIRED CHANGES:
{changes}"""


# --- plumbing -----------------------------------------------------------------

def _parse_json(raw):
    """First JSON object in a model reply, or None. Tolerates code fences."""
    if not raw:
        return None
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    start = s.find("{")
    end = s.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(s[start:end + 1])
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _normalize_report(obj, who):
    if not obj:
        return {"verdict": "issues", "unparseable": True, "issues": [
            {"severity": "major", "quote": "",
             "problem": f"the {who} reply could not be read twice running; "
                        f"this round has no {who} review", "fix": ""}]}
    issues = []
    raw_issues = obj.get("issues")
    for i in raw_issues if isinstance(raw_issues, list) else []:
        if not isinstance(i, dict):
            continue
        sev = str(i.get("severity") or "minor").lower()
        issues.append({"severity": sev if sev in ("critical", "major", "minor") else "minor",
                       "quote": str(i.get("quote") or "")[:500],
                       "problem": str(i.get("problem") or "")[:500],
                       "fix": str(i.get("fix") or "")[:500]})
    verdict = "clean" if not issues else "issues"
    return {"verdict": verdict, "issues": issues}


def _normalize_ruling(obj):
    if not obj:
        return {"ruling": REVISE, "required_changes": [], "dismissed": [],
                "title": "", "rationale": "magistrate reply could not be read",
                "unparseable": True}
    ruling = str(obj.get("ruling") or "").lower().strip()
    if ruling not in (APPROVE, REVISE, REJECT):
        ruling = REVISE
    rc = obj.get("required_changes")
    changes = [str(c) for c in (rc if isinstance(rc, list) else []) if str(c).strip()]
    return {"ruling": ruling, "required_changes": changes,
            "dismissed": [str(d) for d in (obj.get("dismissed") if isinstance(obj.get("dismissed"), list) else [])],
            "title": _clean_title(obj.get("title") if ruling == APPROVE else ""),
            "rationale": str(obj.get("rationale") or "")[:1500]}


def _clean_title(t):
    t = SAN.clean(str(t or "")).strip().strip('"').strip()
    t = re.sub(r"[:#*]", "", t)
    # Never a snow line figure in the title: the list page shows titles, and
    # the terrain-impossible numbers of 09-12/13/15 all lived in titles.
    if re.search(r"\d{1,2},?\d{3}\s*(?:ft|feet|')", t, re.IGNORECASE):
        return ""
    words = t.split()
    if not (2 <= len(words) <= 8) or len(t) > 60:
        return ""
    return t


def _fmt_report(report):
    if report.get("verdict") == "clean":
        return "clean, no issues"
    lines = []
    for i in report.get("issues", []):
        lines.append(f"- [{i['severity']}] \"{i['quote']}\" :: {i['problem']}"
                     + (f" -> {i['fix']}" if i.get("fix") else ""))
    return "\n".join(lines) or "clean, no issues"


def _recent_context(bundle, recent_bodies):
    parts = []
    shapes = bundle.get("recent_posts") or []
    if shapes:
        parts.append("RECENT OPENERS AND CLOSERS:")
        for r in shapes:
            parts.append(f"  {r.get('date')} opened: {r.get('opened')}")
            parts.append(f"  {r.get('date')} closed: {r.get('closed')}")
    for b in (recent_bodies or [])[:2]:
        parts.append("RECENT PUBLISHED POST:\n" + b[:2500])
    return "\n".join(parts) or "(no recent posts on file)"


def _gate_flags(bundle, text, calibrated):
    """What the deterministic gate says about this text, minus the review-
    everything policy flag, which is this panel's job now."""
    verdict, reasons = G.evaluate(bundle, text, first_30_days=False,
                                  calibrated=calibrated)
    return verdict, reasons


# --- the three roles ------------------------------------------------------------

def _ask_json(llm, msgs):
    """One retry on an unreadable reply. Models occasionally wrap JSON in
    prose; a second ask almost always comes back clean."""
    obj = _parse_json(llm(msgs))
    if obj is None:
        obj = _parse_json(llm(msgs + [
            {"role": "assistant", "content": "(unreadable)"},
            {"role": "user", "content": "Reply again with ONLY the JSON object."}]))
    return obj


def fact_check(llm, brief, text):
    msgs = [{"role": "system", "content": FACT_CHECKER_SYSTEM},
            {"role": "user", "content": f"DATA BRIEF:\n{brief}\n\nDRAFT:\n{text}"}]
    return _normalize_report(_ask_json(llm, msgs), "fact checker")


def edit_review(llm, text, bundle, recent_bodies):
    system = EDITOR_SYSTEM.replace("{persona}", CO.load_system_prompt())
    msgs = [{"role": "system", "content": system},
            {"role": "user", "content":
                f"THE FORECASTER'S RECENT POSTS:\n{_recent_context(bundle, recent_bodies)}"
                f"\n\nDRAFT TO REVIEW:\n{text}"}]
    return _normalize_report(_ask_json(llm, msgs), "editor")


def rule(llm, brief, text, facts, editor, gate_verdict, gate_reasons, round_no, rounds):
    gate = ("none" if not gate_reasons else
            f"{gate_verdict.upper()}:\n" + "\n".join(f"- {r}" for r in gate_reasons))
    last = ("\nTHIS IS THE FINAL ROUND. If it is not publishable as written, "
            "REJECT rather than REVISE." if round_no >= rounds else "")
    msgs = [{"role": "system", "content": MAGISTRATE_SYSTEM},
            {"role": "user", "content":
                f"ROUND {round_no} of {rounds}.{last}\n\n"
                f"DATA BRIEF:\n{brief}\n\nDRAFT:\n{text}\n\n"
                f"FACT CHECK REPORT:\n{_fmt_report(facts)}\n\n"
                f"EDITOR REPORT:\n{_fmt_report(editor)}\n\n"
                f"AUTOMATED RULE GATE FLAGS:\n{gate}"}]
    return _normalize_ruling(_ask_json(llm, msgs))


def revise(writer_llm, bundle, slot, text, changes):
    note = REVISER_INSTRUCTION.format(
        draft=text, changes="\n".join(f"- {c}" for c in changes))
    return SAN.clean(CO.compose(bundle, writer_llm, post_type=slot,
                                extra_instruction=note))


# --- the loop -------------------------------------------------------------------

def run_panel(bundle, text, *, slot, writer_llm, review_llm=None, calibrated=False,
              recent_bodies=None, rounds=None, log=print):
    """Returns a dict:
        approved: bool
        text:     the exact text the magistrate ruled on last (publish THIS)
        title:    magistrate's headline on approval, or ""
        rounds:   list of per-round records (for the transcript)
        reason:   one line, why it ended the way it did
    """
    review_llm = review_llm or writer_llm
    rounds = rounds or max_rounds()
    brief = CO.render_bundle(bundle, slot)
    history = []

    for n in range(1, rounds + 1):
        gate_verdict, gate_reasons = _gate_flags(bundle, text, calibrated)
        facts = fact_check(review_llm, brief, text)
        editor = edit_review(review_llm, text, bundle, recent_bodies)
        ruling = rule(review_llm, brief, text, facts, editor,
                      gate_verdict, gate_reasons, n, rounds)

        # The magistrate cannot overrule a hard block. A BLOCK is a fact about
        # the text (an invented gauge number, a present-tense road claim) that
        # a regex has proved; an approval of it is a mistake by definition.
        if ruling["ruling"] == APPROVE and gate_verdict == G.BLOCK:
            ruling["ruling"] = REVISE
            ruling["required_changes"] = (ruling["required_changes"] or []) + [
                f"automated gate still blocks this text: {r}" for r in gate_reasons]
            ruling["rationale"] += " [Approval overridden: the rule gate blocks this text.]"

        # Two reviews or no approval. A magistrate ruling on a missing report
        # is ruling on half the evidence.
        missing = [w for w, r in (("fact checker", facts), ("editor", editor))
                   if r.get("unparseable")]
        if ruling["ruling"] == APPROVE and missing:
            ruling["ruling"] = REVISE
            ruling["required_changes"] = []
            ruling["rationale"] += (f" [Approval withheld: no readable "
                                    f"{' or '.join(missing)} report this round.]")

        record = {"round": n, "text": text, "gate": [gate_verdict, gate_reasons],
                  "fact_check": facts, "editor": editor, "ruling": ruling}
        history.append(record)
        crit = sum(1 for r in (facts, editor) for i in r["issues"]
                   if i["severity"] in ("critical", "major"))
        log(f"panel round {n}/{rounds}: facts={facts['verdict']} "
            f"editor={editor['verdict']} (critical/major={crit}) "
            f"gate={gate_verdict} -> magistrate {ruling['ruling'].upper()}")

        if ruling["ruling"] == APPROVE:
            return {"approved": True, "text": text, "title": ruling.get("title", ""),
                    "rounds": history,
                    "reason": f"approved by the magistrate in round {n}"}
        if ruling["ruling"] == REJECT:
            return {"approved": False, "text": text, "title": "", "rounds": history,
                    "reason": f"rejected by the magistrate in round {n}: "
                              f"{ruling['rationale']}"}
        if n == rounds:
            break

        changes = ruling["required_changes"] or [
            f"{i['quote']} -> {i['fix'] or i['problem']}"
            for r in (facts, editor) for i in r["issues"]
            if i["severity"] in ("critical", "major")]
        if not changes:
            # Nothing concrete to change (e.g. an unreadable ruling): review
            # the same text again rather than rewriting it blind.
            continue
        try:
            revised = revise(writer_llm, bundle, slot, text, changes)
        except Exception as exc:  # noqa: BLE001
            log(f"panel: revision failed ({exc}); reviewing the same text again")
            continue
        if revised and len(revised.strip()) >= 120:
            text = revised

    last = history[-1]["ruling"] if history else {}
    return {"approved": False, "text": text, "title": "", "rounds": history,
            "reason": f"not approved after {rounds} round(s): "
                      f"{last.get('rationale', 'no ruling')}"}


def transcript(result, bundle, slot):
    """Markdown record of every round, committed so the reasoning is auditable."""
    L = [f"# Review panel: {bundle.get('post_for_date')} {slot}", "",
         f"Outcome: **{'APPROVED' if result['approved'] else 'NOT APPROVED'}**, "
         f"{result['reason']}", ""]
    if result.get("title"):
        L += [f"Title: {result['title']}", ""]
    for r in result["rounds"]:
        ru = r["ruling"]
        L += [f"## Round {r['round']}", "",
              "### Draft", "", "```", r["text"].strip(), "```", "",
              f"### Rule gate: {r['gate'][0]}", ""]
        L += [f"- {x}" for x in r["gate"][1]] or ["- nothing flagged"]
        L += ["", "### Fact checker", "", _fmt_report(r["fact_check"]), "",
              "### Editor", "", _fmt_report(r["editor"]), "",
              f"### Magistrate: {ru['ruling'].upper()}", "", ru.get("rationale", ""), ""]
        if ru.get("required_changes"):
            L += ["Required changes:"] + [f"- {c}" for c in ru["required_changes"]] + [""]
        if ru.get("dismissed"):
            L += ["Dismissed:"] + [f"- {d}" for d in ru["dismissed"]] + [""]
    return "\n".join(L) + "\n"
