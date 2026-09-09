"""
The gate. Nothing publishes without passing through here.

The governing asymmetry: silence is recoverable, a confidently wrong 5:45am
forecast is not. People make school, travel and livestock decisions on this.
So every rule below fails toward NOT POSTING, and the ones that involve
life-safety fail toward a human reading it first.

Three tiers:
  PASS   -- publish automatically
  REVIEW -- hold for a person; write the draft to output/ and notify
  BLOCK  -- do not publish, do not queue; something is wrong with the inputs
"""

import re

PASS, REVIEW, BLOCK = "pass", "review", "block"

# Data a forecast cannot be honestly written without. A conditions card can
# survive a missing lake level; a forecast cannot survive a missing forecast.
REQUIRED_SOURCES = ["alerts"]
REQUIRED_BANDS = ["durango", "bayfield", "vallecito"]

# Phrases that would make the forecaster sound like something it is not.
FORBIDDEN_PATTERNS = [
    # Credential claims, in any grammatical dress. The persona is emphatically
    # NOT a credentialed meteorologist, and in a county of 55,000 someone will
    # check. This is the one failure that would be unrecoverable, so the pattern
    # is deliberately broad and a false positive is cheap.
    (r"\b(?:certified|degreed|professional|trained|career)\s+meteorologist\b",
     "claims a credential"),
    (r"\b(?:I am|I'm|as)\s+a\s+meteorologist\b", "claims a credential"),
    (r"\bmy (?:degree|PhD|doctorate|masters|master's|training) in\b",
     "claims a credential"),
    (r"\bI (?:studied|majored in|have a degree in)\b", "claims a credential"),
    (r"\bNational Weather Service (?:has|is) (?:cancel|lift)", "speaks for the NWS"),
    (r"\bschool(?:s)? (?:is|are) (?:closed|cancelled|canceled)\b", "announces a closure decision"),
    (r"\b(?:president|democrat|republican|GOP)\b", "politics"),
    (r"\blake[- ]effect\b", "lake-effect at Vallecito is physically wrong here"),
]

# Live road-status claims. We forecast the passes; we never report their state.
# CDOT's public feed documentation has been withdrawn, so there is no source
# behind a sentence like "Red Mountain is closed" -- and a wrong one sends
# somebody on a three-hour detour or at a pass that is actually shut. Allowed
# only when live roads data is present in the bundle.
ROAD_STATUS_CLAIMS = [
    # Named passes belong in this alternation too: "Red Mountain is closed"
    # names no road noun at all, and that is how a local would actually write
    # it.
    (r"\b(?:pass|passes|road|highway|550|160|240|501|coal bank|molas|"
     r"red mountain|wolf creek)\b[^.\n]{0,50}\b(?:is|are|'s)\s+(?:closed|open)\b",
     "states whether a road is open or closed"),
    (r"\b(?:is|are|'s)\s+(?:closed|open)\b[^.\n]{0,40}\b(?:pass|passes|550|160)\b",
     "states whether a road is open or closed"),
    (r"\bchain law(?:'s| is| are)?\s*(?:on|in effect|up)\b", "asserts chain law status"),
    (r"\btraction law(?:'s| is)?\s*(?:on|in effect|up)\b", "asserts traction law status"),
    (r"\bCDOT has (?:closed|opened|lifted)\b", "asserts a CDOT action"),
    (r"\bthey(?:'re| are) doing control work\b", "asserts avalanche control is underway"),

    # THE GAP THAT SHIPPED. Every pattern above keys on "open" or "closed", so
    # the 2026-09-02 draft sailed through with "The passes are dry, Coal Bank,
    # Molas, Red Mountain and Wolf Creek all clear." That is a road SURFACE
    # claim about four passes with no CDOT data behind it, which is exactly the
    # thing that gets someone over Coal Bank on black ice at 6am believing a
    # weather page told them it was fine.
    #
    # Forecasting the surface is fine and is the whole point of passes.py.
    # Asserting it in the present tense is not. The distinction the patterns
    # draw is tense: "should stay dry" and "any ice would be early" pass;
    # "are dry" and "all clear" do not.
    (r"\b(?:pass|passes|road|roads|highway|550|160|240|501)\b[^.\n]{0,60}"
     r"\b(?:is|are|'s|re)\s+(?:currently\s+)?"
     r"(?:dry|wet|clear|bare|icy|slick|snowpacked|snow[- ]packed|"
     r"plowed|sanded|passable|impassable|fine|good|clean)\b",
     "states a present-tense road surface condition"),
    (r"\b(?:all|both)\s+(?:clear|dry|open|passable)\b[^.\n]{0,60}"
     r"\b(?:pass|passes|coal bank|molas|red mountain|wolf creek|550|160)\b",
     "states a present-tense road surface condition"),
    (r"\b(?:coal bank|molas|red mountain|wolf creek)\b[^.\n]{0,80}"
     r"\b(?:all\s+)?(?:clear|dry|bare|icy|slick|snowpacked|snow[- ]packed)\b"
     r"(?![^.\n]{0,40}\b(?:should|expect|likely|by|through|overnight|"
     r"tonight|tomorrow|forecast)\b)",
     "states a present-tense road surface condition"),
]

# Saying Florida with first-syllable stress is the number one newcomer tell.
#
# CAREFUL: the persona writes the plain word "Florida" constantly and correctly
# -- "the Florida Road," "Vallecito and the Florida," "the Florida drainage."
# Only a PRONUNCIATION GLOSS with first-syllable stress is wrong. So this
# requires an explicit syllable separator, which the ordinary word never has.
# An earlier version omitted that and blocked every correct use of the word.
FLORIDA_MISPRONUNCIATION = re.compile(
    r"\bflor[-\s]+i?h?[-\s]*d(?:a|uh)\b", re.IGNORECASE)


def evaluate(bundle, draft_text, *, first_30_days=False, calibrated=False):
    """Returns (verdict, reasons). Most severe verdict wins."""
    reasons = []
    verdict = PASS

    def escalate(new, why):
        nonlocal verdict
        reasons.append(why)
        order = {PASS: 0, REVIEW: 1, BLOCK: 2}
        if order[new] > order[verdict]:
            verdict = new

    # --- input integrity: BLOCK ------------------------------------------
    missing_required = [s for s in REQUIRED_SOURCES if s in bundle.get("missing", [])]
    if missing_required:
        escalate(BLOCK, f"required source(s) unavailable: {missing_required}")

    bad_bands = [b for b in REQUIRED_BANDS
                 if not bundle.get("bands", {}).get(b, {}).get("ok")]
    if bad_bands:
        escalate(BLOCK, f"forecast unavailable for band(s): {bad_bands} -- "
                        "a partial elevation forecast is worse than none")

    if not draft_text or len(draft_text.strip()) < 120:
        escalate(BLOCK, "draft is empty or implausibly short")

    # --- content safety: BLOCK -------------------------------------------
    for pattern, why in FORBIDDEN_PATTERNS:
        if re.search(pattern, draft_text, re.IGNORECASE):
            escalate(BLOCK, f"draft {why}")
    if FLORIDA_MISPRONUNCIATION.search(draft_text):
        escalate(BLOCK, "draft mispronounces Florida (it is fluh-REE-duh)")

    # Road status without a road-status source.
    if not bundle.get("roads"):
        for pattern, why in ROAD_STATUS_CLAIMS:
            if re.search(pattern, draft_text, re.IGNORECASE):
                escalate(BLOCK, f"draft {why} with no live CDOT data behind it -- "
                                "forecast the passes, link CDOT for status")
                break

    # The persona rule "never a percentage," which the prompt has always
    # stated and nothing has ever enforced. The 2026-09-08 draft: "Pop's at 4%
    # this afternoon which is basically nothing." A probability of
    # precipitation expressed as a number is exactly the forecaster-voice tic
    # this persona is built to avoid; uncertainty is supposed to be expressed
    # by naming which models disagree.
    #
    # Two percentages are legitimate and must pass: percent of median, which is
    # the standard snowpack unit and appears in the local-language list, and
    # percent of full pool, which is how reservoir storage is reported.
    for m in re.finditer(r"\d+(?:\.\d+)?\s*(?:%|percent)", draft_text or "",
                         re.IGNORECASE):
        tail = draft_text[m.end():m.end() + 30].lower()
        if re.match(r"\s*(?:of\s+)?(?:median|average|full pool|capacity|normal)",
                    tail):
            continue
        escalate(BLOCK, f"draft states a bare percentage ({m.group(0).strip()!r}); "
                        "this voice never gives one, it names which models "
                        "disagree instead")
        break

    # Should be unreachable: sanitize.clean() runs first. If this fires, the
    # sanitizer has a gap worth knowing about rather than shipping past.
    from . import sanitize as _san
    tells = _san.has_tells(draft_text)
    if tells:
        escalate(BLOCK, f"draft still contains {', '.join(tells)} after sanitising")

    # --- life safety: REVIEW ---------------------------------------------
    if bundle.get("life_safety_alerts"):
        events = sorted({a["event"] for a in bundle["life_safety_alerts"]})
        escalate(REVIEW, f"active life-safety alert(s): {events}")

    if re.search(r"burn scar|416 (?:fire|scar)|missionary ridge", draft_text, re.IGNORECASE):
        escalate(REVIEW, "mentions a burn scar -- debris flows here have been "
                         "triggered by ordinary sub-two-year storms")

    if re.search(r"\bavalanche\b", draft_text, re.IGNORECASE):
        escalate(REVIEW, "mentions avalanche conditions -- link CAIC, never interpret")

    # --- forecast discipline: REVIEW -------------------------------------
    if _states_snow_beyond_3_days(draft_text, bundle):
        escalate(REVIEW, "appears to state snow amounts beyond day 3")

    if bundle.get("snow_line") and not calibrated:
        if not re.search(r"grain of salt|uncertain|could go either way|rough|best guess|not settled",
                         draft_text, re.IGNORECASE):
            escalate(REVIEW, "publishes an uncalibrated snow line without a hedge")

    if first_30_days:
        escalate(REVIEW, "first-30-days policy: review everything")

    return verdict, reasons


_DAY_WORDS = r"(?:four|five|six|seven|next week|late next week)"


def _states_snow_beyond_3_days(text, bundle):
    """Rough check for the cardinal sin: a snow number attached to a far-out day.

    Deliberately conservative -- it escalates to REVIEW, not BLOCK, because a
    false positive that makes a person glance at a draft costs almost nothing
    and a false negative costs the brand.
    """
    window = re.compile(
        rf"\d+\s*(?:-\s*\d+)?\s*(?:\"|inch|inches|in\b|ft|feet)[^.\n]{{0,80}}{_DAY_WORDS}",
        re.IGNORECASE)
    if window.search(text):
        return True
    reverse = re.compile(
        rf"{_DAY_WORDS}[^.\n]{{0,80}}\d+\s*(?:-\s*\d+)?\s*(?:\"|inch|inches)",
        re.IGNORECASE)
    return bool(reverse.search(text))


def require_or_abort(bundle):
    """Hard precondition check before we even call the LLM.

    Saves a model call, and more importantly makes 'we had no data' a distinct,
    loudly-logged outcome rather than something the composer papers over.
    """
    problems = []
    if "alerts" in bundle.get("missing", []):
        problems.append("NWS alerts unavailable")
    for b in REQUIRED_BANDS:
        if not bundle.get("bands", {}).get(b, {}).get("ok"):
            problems.append(f"no forecast for {b}")
    return problems


# --- self-correction -------------------------------------------------------
#
# A BLOCK is not one thing. Two of them mean the data is wrong and no amount of
# rewriting will help. The rest mean the model wrote a sentence it was told not
# to write, and it will almost always fix that if you show it the complaint.
#
# This distinction is what turns a blocked morning into a published one. On
# 2026-09-08 the run landed on time, built a complete and accurate forecast,
# and was blocked over a single sentence: "The passes are dry." Blocking was
# right, the sentence was a road-status claim with no CDOT data behind it. But
# the outcome was a silent morning, which is the failure the whole rebuild was
# supposed to stop. One rewrite costs a few cents and about ten seconds.

_DATA_BLOCK_PREFIXES = (
    "required source(s) unavailable",
    "forecast unavailable for band(s)",
    "draft is empty",
)


def text_fixable(reasons):
    """True when every reason is about the writing rather than the inputs."""
    if not reasons:
        return False
    return not any(r.startswith(_DATA_BLOCK_PREFIXES) for r in reasons)


def correction_note(reasons):
    """The instruction handed back to the model on a rewrite.

    Phrased as a specific edit, not as a scolding and not as a restatement of
    the rules it already has. A model given "you violated rule 7" tends to
    rewrite everything and lose the good parts; a model given "that one
    sentence, here is why, change only it" keeps the post.
    """
    bullets = "\n".join(f"  - {r}" for r in reasons)
    return (
        "YOUR PREVIOUS DRAFT WAS REJECTED BY THE PUBLISHING GATE.\n\n"
        "Write the post again. Keep everything that was right: the same "
        "forecast, the same numbers, the same structure, the same voice. "
        "Change only what these complaints name.\n\n"
        f"{bullets}\n\n"
        "On road and pass conditions specifically, if that is what was "
        "flagged: you have weather data, not road data. Never write that a "
        "pass or road IS dry, clear, icy, open or closed. Forecast it instead, "
        "in the future or conditional, and point at CDOT for the status. "
        "'Coal Bank should stay dry through the morning' is right. "
        "'The passes are dry' is not.\n\n"
        "Return only the post."
    )
