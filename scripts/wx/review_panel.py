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

# Rules both reviewers and the magistrate must apply the same way. The first
# two smoke tests (2026-09-25) were rejected largely because they did not:
# the fact checker demanded exact figures while the editor demanded ranges,
# each rewrite of one review undid the other, and the fact checker rejected the
# harness's own timestamp as fabricated.
SHARED_RULES = """RULES THAT BIND EVERYONE ON THIS PANEL:
1. NUMBERS. The persona asks for ranges and the brief holds exact figures, and both are satisfied by a range or a rounded phrase that CONTAINS the brief's figure: "0.7-0.8in" or "close to an inch" for 0.79, "a few hundredths" for 0.03. Do not demand exact digits, and do not demand a range where a rounded phrase already contains the figure. Quoting a model's own total ("the Euro has 0.93in") is not a forecast point value. A number is wrong only when it is outside what the brief supports, or is not in the brief at all. Never propose a replacement number that is not in the brief.
2. THE STAMP. The first line of the draft begins with a timestamp such as "09/25/26 5:52am:". Check the DATE against the brief's "Open with the stamp" line and nothing else. The CLOCK TIME is the time the post goes out, which the brief states; it is NOT the time the post was written, and COMPOSED AT is NOT evidence about it. An evening run writes the next morning's post, so a stamp hours ahead of COMPOSED AT is correct and expected. Never call the stamp fabricated, invented or wrong because it differs from COMPOSED AT; that reasoning is always an error, and on 2026-09-25 it cost a sound post its publication. Never flag or demand a "late start" clause either: the brief's RUNNING LATE line decides that.
3. GUST UNITS. "mph" after a gust range is optional. Never flag its presence or its absence.
4. ONE PERSONAL DETAIL. It carries no measurement unless the brief's gauge block gives one. Where it says NO READING TODAY, a replacement must not contain a gauge or stake figure ("the gauge caught 0.08" is forbidden), only something like the sky, the yard, the truck or the dog.
5. NO INVENTION IN A FIX. A fix or replacement may not add any number, name, reading or event that is not in the brief or already in the draft. If you cannot write a safe fix, leave it empty and describe the problem.
6. WHEN THE TWO REVIEWS CONFLICT, the fact checker wins on numbers, timing and alerts, and the editor wins on voice, format and repetition. A fix must satisfy both."""

_REPORT_SHAPE = """Reply with ONE JSON object and nothing else, compact, under 25 lines. Inside a JSON string write every double quote (an inch mark included) as \\" so the JSON stays valid.
{
  "verdict": "clean" or "issues",
  "issues": [
    {"severity": "critical" | "major" | "minor",
     "quote": "<the exact sentence from the draft>",
     "problem": "<what is wrong, one sentence>",
     "evidence": "<the line of the data brief that proves it, copied character for character; or exactly NOT IN BRIEF when the draft states something the brief does not contain; or exactly PERSONA when it breaks a persona rule>",
     "fix": "<the replacement sentence, written in the forecaster's voice, or empty>"}
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

Before you flag ANY timing or amount claim, find the brief's time-window line \
for that band, compare the actual numbers (a 00:00-05:00 window is overnight, \
before a 6:30 school call; 06:00-11:00 is the morning), and copy that line into \
"evidence". If you cannot find a brief line that contradicts the draft, do not \
flag it. Every flag needs evidence; a flag whose evidence is not in the brief is \
discarded.

""" + SHARED_RULES + "\n\n" + _REPORT_SHAPE

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

You are also given the data brief the writer had. It is for reference: the fact \
checker owns every number, so you never invent one. When the rulebook calls \
"The gauge showed 0.12 overnight" a good personal detail, that is only when \
the brief's gauge block carries a reading; otherwise the detail has no number.

""" + SHARED_RULES + "\n\n" + _REPORT_SHAPE

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
- Required changes are small edits to the text as written, at most 8, most \
important first. Never ask the writer to restructure the post, and never put a \
number or fact in a replacement that the brief does not contain. If two \
reviewer fixes conflict, resolve them by the rules below and give ONE change.
- A reviewer issue whose evidence is missing, or does not match the brief, is \
not an issue: dismiss it.

""" + SHARED_RULES + """

Reply with ONE JSON object and nothing else, compact, under 30 lines. Inside \
a JSON string write every double quote (an inch mark included) as \\" so the \
JSON stays valid:
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
If a required change's wording contains a number, a gauge or stake reading, or \
an event that is not in your brief, that wording is a mistake: keep what the \
change is asking for, drop the invented detail, and never turn the first line \
into anything but the assigned stamp followed by your greeting. Return only \
the post, starting with the date stamp.

YOUR CURRENT DRAFT:
{draft}

REQUIRED CHANGES:
{changes}"""


# --- plumbing -----------------------------------------------------------------

def _strict_object(s):
    try:
        obj = json.loads(s)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _escape_stray_quotes(s):
    """Escape a double quote inside a JSON string when it is plainly text.

    The reviewers quote sentences that carry inch marks (0.05" through
    mid-morning). A quote closes a string only when what follows it is what
    can follow a string here: a colon (a key), a closing bracket or brace, or a
    comma followed by the start of another string or container. Anything else
    is text. Every value in this schema is a string, an array or an object, so
    a comma followed by a digit or a word is not a boundary.
    """
    out, in_str, i, n = [], False, 0, len(s)
    while i < n:
        c = s[i]
        if in_str and c == "\\" and i + 1 < n:
            out.append(c + s[i + 1])
            i += 2
            continue
        if c == '"':
            if not in_str:
                in_str = True
                out.append(c)
            else:
                j = i + 1
                while j < n and s[j] in " \t\r\n":
                    j += 1
                nxt = s[j] if j < n else ""
                closes = nxt in (":", "}", "]", "")
                if nxt == ",":
                    k = j + 1
                    while k < n and s[k] in " \t\r\n":
                        k += 1
                    closes = k >= n or s[k] in '"{['
                if closes:
                    in_str = False
                    out.append(c)
                else:
                    out.append('\\"')
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _close_truncated(s):
    """Close a reply cut off mid-string by max_tokens: end the open string and
    close whatever brackets are still open."""
    stack, in_str, i, n = [], False, 0, len(s)
    while i < n:
        c = s[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c in "{[":
            stack.append("}" if c == "{" else "]")
        elif c in "}]" and stack:
            stack.pop()
        i += 1
    if not stack and not in_str:
        return s
    tail = s.rstrip()
    # A dangling half of a pair ("key": or a trailing comma) cannot be closed.
    if not in_str:
        tail = re.sub(r"[,:]\s*$", "", tail)
    return tail + ('"' if in_str else "") + "".join(reversed(stack))


def _lenient_object(s):
    """Parse a model's JSON reply, repairing the damage models actually do:
    unescaped inch marks, a trailing comma, a reply cut off by max_tokens."""
    obj = _strict_object(s)
    if obj is not None:
        return obj
    fixed = re.sub(r",\s*([}\]])", r"\1", _escape_stray_quotes(s))
    obj = _strict_object(fixed)
    if obj is not None:
        return obj
    closed = _close_truncated(fixed)
    obj = _strict_object(closed)
    if obj is not None:
        obj["_truncated"] = True
        return obj
    # Truncated inside an element that would not close cleanly: drop back to
    # the last comma and close there, a few times at most.
    cut = fixed
    for _ in range(6):
        cut = cut[:cut.rfind(",")] if "," in cut else ""
        if not cut:
            break
        obj = _strict_object(_close_truncated(cut))
        if obj is not None:
            obj["_truncated"] = True
            return obj
    return None


def _parse_json(raw):
    """First JSON object in a model reply, or None. Tolerates code fences,
    prose around the object, and the repairs in _lenient_object."""
    if not raw:
        return None
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    start = s.find("{")
    if start < 0:
        return None
    end = s.rfind("}")
    obj = None
    if end > start:
        obj = _lenient_object(s[start:end + 1])
    if obj is None:
        # No closing brace, or the text between was unrepairable: the reply
        # may simply have been cut off.
        obj = _lenient_object(s[start:])
    # "{" repairs to an object holding nothing but our own marker. That is not
    # a reply.
    return obj if obj and any(not k.startswith("_") for k in obj) else None


def _salvage_ruling(raw):
    """A ruling out of a reply that will not parse at all. Only revise or
    reject: an approval must come from a reply that parsed whole, because an
    approval publishes to the site and half a reply is not a signature."""
    m = re.search(r'"ruling"\s*:\s*"(revise|reject)"', raw or "", re.IGNORECASE)
    return m.group(1).lower() if m else None


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _evidence_ok(evidence, brief):
    """Is the fact checker's evidence real? It is when it says NOT IN BRIEF or
    PERSONA, or when at least one quoted line is actually in the brief."""
    ev = str(evidence or "").strip()
    if not ev:
        return False
    if ev.upper().startswith(("NOT IN BRIEF", "PERSONA")):
        return True
    hay = _norm(brief)
    parts = [p for p in re.split(r"\s*(?:\||\.\.\.|;|\n)\s*", ev) if len(p.strip()) >= 6]
    return any(_norm(p).strip(" .") in hay for p in parts or [ev])


def _normalize_report(obj, who, diag=None, brief=None):
    if not obj:
        rep = {"verdict": "issues", "unparseable": True, "issues": [
            {"severity": "major", "quote": "",
             "problem": f"the {who} reply could not be read twice running; "
                        f"this round has no {who} review", "evidence": "", "fix": ""}]}
        if diag:
            rep["raw_reply"], rep["stop_reason"] = diag["raw"], diag.get("stop")
        return rep
    issues = []
    raw_issues = obj.get("issues")
    for i in raw_issues if isinstance(raw_issues, list) else []:
        if not isinstance(i, dict):
            continue
        sev = str(i.get("severity") or "minor").lower()
        sev = sev if sev in ("critical", "major", "minor") else "minor"
        issue = {"severity": sev,
                 "quote": str(i.get("quote") or "")[:500],
                 "problem": str(i.get("problem") or "")[:500],
                 "evidence": str(i.get("evidence") or "")[:500],
                 "fix": str(i.get("fix") or "")[:500]}
        # The fact checker's two false alarms on 2026-09-25 (timing "after the
        # school run" against a 00:00-05:00 window, a "fabricated" stamp) both
        # came with no brief line behind them. A flag that cannot point at the
        # brief is an opinion, and an opinion cannot block a publish.
        if (brief is not None and sev in ("critical", "major")
                and not _evidence_ok(issue["evidence"], brief)):
            issue["severity"] = "minor"
            issue["problem"] = "(no matching brief line, downgraded) " + issue["problem"]
        issues.append(issue)
    if obj.get("_truncated") and not issues:
        # Cut off before any issue made it out. Repairing that gives an empty
        # list, which reads as "clean", and a reviewer that ran out of room is
        # the opposite of a clean bill of health.
        return _normalize_report(None, who, {"raw": json.dumps(obj), "stop": "max_tokens"})
    verdict = "clean" if not issues else "issues"
    return {"verdict": verdict, "issues": issues}


def _normalize_ruling(obj, diag=None):
    if not obj:
        salvaged = _salvage_ruling(diag["raw"]) if diag else None
        rep = {"ruling": salvaged or REVISE, "required_changes": [], "dismissed": [],
               "title": "", "unparseable": True,
               "rationale": ("magistrate reply could not be read"
                             + (f"; the ruling {salvaged.upper()} was recovered from it"
                                if salvaged else ""))}
        if diag:
            rep["raw_reply"], rep["stop_reason"] = diag["raw"], diag.get("stop")
        return rep
    ruling = str(obj.get("ruling") or "").lower().strip()
    if ruling not in (APPROVE, REVISE, REJECT):
        # A garbled value ('reject" <<< junk') still says which way it went,
        # but only in the safe directions: never an approval.
        m = re.match(r"(revise|reject)\b", ruling)
        ruling = m.group(1) if m else REVISE
    note = ""
    if ruling == APPROVE and obj.get("_truncated"):
        # An approval publishes to the site unattended. A reply that was cut
        # off mid-sentence is not a signature, even when the word "approve"
        # made it out before the cut.
        ruling = REVISE
        note = "approval came from a reply that was cut off, so it does not count. "
    rc = obj.get("required_changes")
    changes = [str(c) for c in (rc if isinstance(rc, list) else []) if str(c).strip()]
    return {"ruling": ruling, "required_changes": changes,
            "dismissed": [str(d) for d in (obj.get("dismissed") if isinstance(obj.get("dismissed"), list) else [])],
            "title": _clean_title(obj.get("title") if ruling == APPROVE else ""),
            "rationale": (note + str(obj.get("rationale") or ""))[:1500]}


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
                     + (f" (evidence: {i['evidence']})" if i.get("evidence") else "")
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
    """(object, diagnostics). One retry on an unreadable reply, and the retry
    shows the model its own bad reply, because "(unreadable)" tells it nothing.

    diagnostics is None on success. On failure it keeps the raw reply and the
    stop reason: the magistrate's round-1 reply was unreadable on both smoke
    tests and nothing was kept, so the cause (a cut-off at max_tokens, or a
    stray quote) was a guess. `stop == "max_tokens"` settles it next time.
    """
    raw = llm(msgs)
    obj = _parse_json(raw)
    if obj is not None:
        return obj, None
    stop = getattr(llm, "last_stop_reason", None)
    retry = llm(msgs + [
        {"role": "assistant", "content": (raw or "(empty)")[:6000]},
        {"role": "user", "content":
            "That was not valid JSON"
            + (" (it was cut off at the length limit; be much shorter)"
               if stop == "max_tokens" else "")
            + ". Reply again with ONLY the JSON object, compact, every double "
              "quote inside a string written as \\\"."}])
    obj = _parse_json(retry)
    if obj is not None:
        return obj, None
    return None, {"raw": (retry or raw or "")[:3000],
                  "stop": getattr(llm, "last_stop_reason", None) or stop}


def fact_check(llm, brief, text):
    msgs = [{"role": "system", "content": FACT_CHECKER_SYSTEM},
            {"role": "user", "content": f"DATA BRIEF:\n{brief}\n\nDRAFT:\n{text}"}]
    obj, diag = _ask_json(llm, msgs)
    return _normalize_report(obj, "fact checker", diag, brief=brief)


def edit_review(llm, text, bundle, recent_bodies, brief=None):
    system = EDITOR_SYSTEM.replace("{persona}", CO.load_system_prompt())
    # The editor gets the brief so its fixes can only draw on numbers and
    # readings that exist. Without it, on 2026-09-25 it wrote replacements
    # containing "The gauge caught 0.08 overnight" and "2-4 inches" out of the
    # persona's own examples, and the reviser dutifully used them.
    brief = brief or CO.render_bundle(bundle, "school_call")
    msgs = [{"role": "system", "content": system},
            {"role": "user", "content":
                f"DATA BRIEF THE WRITER HAD (reference only):\n{brief}\n\n"
                f"THE FORECASTER'S RECENT POSTS:\n{_recent_context(bundle, recent_bodies)}"
                f"\n\nDRAFT TO REVIEW:\n{text}"}]
    obj, diag = _ask_json(llm, msgs)
    return _normalize_report(obj, "editor", diag)


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
    obj, diag = _ask_json(llm, msgs)
    return _normalize_ruling(obj, diag)


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
        editor = edit_review(review_llm, text, bundle, recent_bodies, brief=brief)
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
        for who, rep in (("fact checker", facts), ("editor", editor),
                         ("magistrate", ruling)):
            if rep.get("unparseable"):
                log(f"panel round {n}: unreadable {who} reply "
                    f"(stop_reason={rep.get('stop_reason')}); kept in the transcript")
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
        for who, rep in (("Fact checker", r["fact_check"]), ("Editor", r["editor"]),
                         ("Magistrate", ru)):
            if rep.get("raw_reply") is not None:
                L += [f"{who} reply that could not be read "
                      f"(stop_reason={rep.get('stop_reason')}):", "", "```",
                      rep["raw_reply"], "```", ""]
    return "\n".join(L) + "\n"
