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
