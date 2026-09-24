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

# Route numbers.
#
# A bare 550 or 160 is not automatically a road. This persona writes elevations
# as "(6,500')" and flows as "running 160 cfs", and a word boundary sits on
# both sides of the number in each case, so `\b501\b` matched them. That is how
# "Durango and the Animas Valley (6,500') stay dry today" -- a weather sentence
# with no road in it at all -- read as a road-status claim.
#
# tools/draft-lint.mjs solved this by requiring the article ("the 550"), which
# is how the persona usually writes it. That costs the unadorned "550 is
# closed", so instead the number stays bare and the two numeric contexts are
# excluded directly: nothing may run into it from the left, which is what the
# comma in "6,500" does, and no unit may follow it. US-550, CR 501 and "the
# 160" all still match.
_ROUTE = (r"(?<![\d,])(?:550|160|172|240|500|501)"
          r'(?!\s*(?:cfs|ft|feet|af|%|,\d|[\'"]))')

# Live road-status claims. We forecast the passes; we never report their state.
# CDOT's public feed documentation has been withdrawn, so there is no source
# behind a sentence like "Red Mountain is closed" -- and a wrong one sends
# somebody on a three-hour detour or at a pass that is actually shut. Allowed
# only when live roads data is present in the bundle.
# Open/closed lives in CLOSURE_CLAIMS below, which is not hedgeable. What
# remains here is judged per clause and yields to a forecast.
ROAD_STATUS_CLAIMS = [
    (r"\bchain law(?:'s| is| are)?\s*(?:on|in effect|up)\b", "asserts chain law status"),
    (r"\btraction law(?:'s| is)?\s*(?:on|in effect|up)\b", "asserts traction law status"),
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
    (rf"\b(?:pass|passes|road|roads|highway|{_ROUTE})\b[^.\n]{{0,60}}"
     r"\b(?:is|are|'s|re)\s+(?:currently\s+)?"
     r"(?:dry|wet|clear|bare|icy|slick|snowpacked|snow[- ]packed|"
     r"plowed|sanded|passable|impassable|fine|good|clean)\b",
     "states a present-tense road surface condition"),
    (rf"\b(?:all|both)\s+(?:clear|dry|open|passable)\b[^.\n]{{0,60}}"
     rf"\b(?:pass|passes|coal bank|molas|red mountain|wolf creek|{_ROUTE})\b",
     "states a present-tense road surface condition"),
    (r"\b(?:coal bank|molas|red mountain|wolf creek)\b[^.\n]{0,80}"
     r"\b(?:all\s+)?(?:clear|dry|bare|icy|slick|snowpacked|snow[- ]packed)\b"
     r"(?![^.\n]{0,40}\b(?:should|expect|likely|by|through|overnight|"
     r"tonight|tomorrow|forecast)\b)",
     "states a present-tense road surface condition"),
]

# THE SECOND GAP. Every pattern in ROAD_STATUS_CLAIMS is anchored on a verb --
# "X is dry", "X are clear" -- so a surface claim with the verb left out is
# invisible to it. Four of the five drafts to 2026-09-24 made one:
#
#   "Dry roads for the bus run this morning."
#   "Bayfield and up the Pine same story, dry pavement and clear conditions."
#
# Those went out to review as PASS-on-this-rule, which meant correction_note()
# never fired and the model was never asked to rewrite them. tools/draft-lint.mjs
# caught them hours later on the review issue, because its rule 2 does carry an
# adjective-first pattern. Two gates for one rule had drifted apart, and the one
# that runs early enough to fix anything was the weaker of the two.
#
# So this mirrors draft-lint.mjs rule 2 on purpose: same surface words, same
# clause split, same hedge list, same conditional-opener rule. The two are meant
# to agree, and where they disagree scripts/wx/prompts/system.md decides.
#
# Tense is the whole distinction, exactly as above. "I'd expect dry pavement by
# the 6:30 call" is the phrasing system.md asks for and must pass; "dry roads
# for the 6:30 call" is the phrasing it forbids and must not.
_SURFACE = (r"dry|wet|icy|slick|snow[- ]?packed|clear|closed|open|plowed|bare|"
            r"greasy|sanded|passable|impassable|fine|good|clean")
_ROAD_NOUN = r"roads?|pavement|highways?|blacktop"
# Route numbers come from _ROUTE, so this rule and the ones above agree about
# what counts as a road and neither of them reads an elevation as one.
_ROAD_NAME = (rf"pass|passes|coal bank|molas|red mountain|wolf creek|cumbres|"
              rf"lizard head|hesperus|florida road|vallecito road|"
              rf"bayfield parkway|elmore|middle mountain road|"
              rf"missionary ridge road|{_ROUTE}")

# "clear roads", "dry pavement" -- a condition with no verb at all.
#
# The lookbehind is load-bearing. "wet" is a verb as often as an adjective in
# this register, and "enough to wet pavement for the evening commute" is a
# forecast of what the rain will do, not a report of what the road is. An
# infinitive is never a present-tense claim.
_ROAD_NOUN_CLAIM = re.compile(
    rf"(?<!\bto )\b(?:{_SURFACE})\s+(?:{_ROAD_NOUN})\b", re.IGNORECASE)

# The telegraphic form, noun then adjective, copula dropped: system.md forbids
# "Roads wet, no ice." by name. The trailing lookahead keeps it to that clipped
# register -- the adjective has to end the clause -- so an ordinary noun phrase
# like "Vallecito Road, fine gravel past the turn" is not a road-status claim.
_ROAD_TELEGRAPHIC_CLAIM = re.compile(
    rf"\b(?:{_ROAD_NOUN})\s+(?:{_SURFACE})\s*(?=[,.;:!?]|$)", re.IGNORECASE)

# "the 501 is fine", "Molas stays clear", "the passes are getting wet pavement".
# "getting" is here because the brief used to ask for it in as many words.
_ROAD_STATE_CLAIM = re.compile(
    rf"\b(?:{_ROAD_NAME}|{_ROAD_NOUN})\b[^.\n]{{0,50}}?"
    rf"(?:\b(?:is|are|'s|re|remains?|sits?|stays?|looks?|runs?|"
    rf"(?:is|are)\s+getting)|\w's)\s+"
    rf"(?:still\s+|both\s+|all\s+|already\s+|completely\s+)?"
    rf"(?:{_SURFACE})\b", re.IGNORECASE)

# CLOSURES ARE NOT HEDGEABLE. This is the one road rule the hedge tiers below
# do not apply to.
#
# A weather-contingent conditional opener still exempts it, deliberately: "If
# CDOT has closed the 550, the detour through Pagosa is long" does not claim
# the 550 is closed. A reader-addressed one does not exempt anything -- see
# _READER_ADDRESSED below.
#
# A surface forecast is a weather claim: we have the weather, so "Coal Bank
# should stay rain at pass level" is ours to make and hedging is exactly what
# makes it honest. Whether a gate is down is not weather. It is an operational
# decision that CDOT makes and publishes, we have no feed for it, and a
# forecast of one is not a hedged version of a fact we hold -- it is invention
# about somebody else's decision. "Wolf Creek will likely be closed if this
# verifies" reads to a parent at 5:45am exactly like "Wolf Creek is closed",
# and both send the same person on the same three-hour detour.
#
# So the verb set is deliberately wide where the surface rules are narrow: the
# copulas, the modal forms ("will be closed", "should stay open"), and the
# plain verbs ("closes at six", "reopens"). Chain law and traction law are NOT
# here -- constants.py holds up "expect traction law by morning" as the honest
# product, and tests/test_passes.py pins that. Those stay hedgeable above.
_CLOSURE_STATE = (
    r"(?:\b(?:is|are|'s|re|was|were|be|been|being|gets?|got|stays?|stayed|"
    r"remains?|remained)\s+(?:still\s+|already\s+|back\s+|all\s+)?"
    r"(?:closed|open|shut)\b|\bclos(?:e|es|ing|ed)\b|\breopen(?:s|ed|ing)?\b|"
    r"\bshuts?\b)")

CLOSURE_CLAIMS = [
    (rf"\b(?:{_ROAD_NAME}|{_ROAD_NOUN})\b[^.\n]{{0,50}}{_CLOSURE_STATE}",
     "states whether a road is open or closed"),
    (rf"{_CLOSURE_STATE}[^.\n]{{0,40}}\b(?:{_ROAD_NAME})\b",
     "states whether a road is open or closed"),
    (r"\bCDOT has (?:closed|opened|lifted)\b", "asserts a CDOT action"),
]


# Hedges, in two tiers, because they are not all the same thing.
#
# A MODAL turns the clause into a forecast outright. system.md lists "should",
# "I'd expect" and "looks like it'll" as the required repairs, so all three
# have to count or the gate contradicts the prompt.
_MODAL_HEDGE = re.compile(
    r"\b(?:should|shouldn't|will|won't|\w+'ll|\w+'d|would|expect|expected|"
    r"likely|probably|could|may|might|if|watch for|look for|plan (?:on|for)|"
    r"forecast)\b", re.IGNORECASE)

# A TIME WINDOW only says when, and on its own it does not make a present
# indicative into a forecast. "The passes are dry through the morning" asserts
# that they are dry, right now, and a reader can drive up and disprove it --
# which is the persona's test. Treating "through the morning" as a hedge
# outright is a hole: the flat patterns have always blocked that sentence, and
# running them through an undifferentiated hedge list would have opened it.
# "should be dry through the morning" is still fine, on the modal.
_TIME_HEDGE = re.compile(
    r"\b(?:by (?:mid|late|early|noon|dark|the|\d)|tonight|tomorrow|later|until|"
    r"through (?:the )?(?:morning|afternoon|evening|day|night|weekend|school run)|"
    r"this (?:afternoon|evening)|all day)\b", re.IGNORECASE)

_PRESENT_INDICATIVE = re.compile(r"(?:\b(?:is|are|'s|re)|\w's)\b", re.IGNORECASE)


def _clause_is_hedged(clause):
    """Is this clause a forecast rather than a report?"""
    if _MODAL_HEDGE.search(clause):
        return True
    return bool(_TIME_HEDGE.search(clause)
                and not _PRESENT_INDICATIVE.search(clause))

# A sentence that opens conditionally hedges every clause in it, including the
# ones after "and": "If that band sets up, the 550 is icy by 6am and Molas is
# slick" is a forecast throughout.
_CONDITIONAL_OPEN = re.compile(r"^(?:if|when|once|unless|should)\b", re.IGNORECASE)

# Unless the conditional is about the READER rather than about the weather.
#
# "If that band sets up" makes everything after it contingent, because what is
# uncertain is the forecast. "If you are heading north" makes nothing
# contingent: it picks out an audience and then states a flat fact at them, so
# "If you are heading north, Red Mountain is closed" is a closure claim wearing
# conditional dress, and it is the form a local would actually write.
#
# The distinction is the subject of the conditional -- a person, or the
# weather. "we" is deliberately absent: the persona writes "If we do see rain
# it'd be brief," which is forecast-contingent, not an address to anybody.
_READER_ADDRESSED = re.compile(
    r"^(?:if|when|once|unless)\s+(?:you|your|you're|youre|ya|anyone|anybody|"
    r"someone|somebody|folks|people|drivers?|kids|the kids)\b", re.IGNORECASE)


# "if" is also in the modal tier, for the trailing form ("the 550 is icy if
# that band sets up"), and at the head of a reader-addressed sentence it would
# hedge the clause all over again: "If you're running the 550 this morning, the
# pass is icy" is one clause and contains an "if". So the opener is dropped
# before the clause is judged. What is left, "you're running the 550 this
# morning, the pass is icy", is the claim actually being made.
_LEADING_CONDITIONAL = re.compile(r"^(?:if|when|once|unless)\s+", re.IGNORECASE)


def _sentence_is_conditional(sentence):
    """Does opening on "if" make the rest of this sentence contingent?"""
    return bool(_CONDITIONAL_OPEN.search(sentence)
                and not _READER_ADDRESSED.search(sentence))


def _claim_body(sentence):
    """The sentence with a reader-addressing opener removed."""
    if _READER_ADDRESSED.search(sentence):
        return _LEADING_CONDITIONAL.sub("", sentence)
    return sentence

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_CLAUSE_SPLIT = re.compile(r",\s*(?:and|but)\s+|;\s*|\s+and\s+|\s+but\s+",
                           re.IGNORECASE)


def road_status_claim(text):
    """(sentence, why) for the first road-status claim, or (None, None).

    One clause walk for both rule sets. ROAD_STATUS_CLAIMS used to be matched
    flat against the whole draft, which made it the only road rule in the
    project with no notion of tense: it blocked "If that band sets up, the 550
    is icy by 6am", a forecast, and it blocked "expect chain law up on Red
    Mountain by morning", which is the phrasing constants.py holds up as the
    honest product. Both now pass on the modal, and everything is judged per
    clause, so a "should" in one half of a sentence cannot launder "the 501 is
    fine" in the other.

    CLOSURE_CLAIMS is the exception: the hedge tiers do not apply to it, though
    a weather-contingent conditional opener still does. Surface is weather and
    is ours to forecast; a gate being down is CDOT's decision and is not ours
    to predict at all.
    """
    for sentence in _SENTENCE_SPLIT.split((text or "").replace("\n", " ")):
        sentence = sentence.strip()
        if not sentence:
            continue
        if _sentence_is_conditional(sentence):
            continue
        body = _claim_body(sentence)
        # Ahead of the hedge tiers, which do not apply to it: see CLOSURE_CLAIMS.
        for pattern, why in CLOSURE_CLAIMS:
            if re.search(pattern, body, re.IGNORECASE):
                return sentence, why
        for clause in _CLAUSE_SPLIT.split(body):
            if not clause or _clause_is_hedged(clause):
                continue
            for pattern, why in ROAD_STATUS_CLAIMS:
                if re.search(pattern, clause, re.IGNORECASE):
                    return sentence, why
            if (_ROAD_NOUN_CLAIM.search(clause)
                    or _ROAD_TELEGRAPHIC_CLAIM.search(clause)
                    or _ROAD_STATE_CLAIM.search(clause)):
                return sentence, "states a present-tense road surface condition"
    return None, None


# A reading attributed to the gauge or the snow stake at the house.
#
# 2026-09-17: "the snow stake here is still sitting at 5 inches" on an all-rain
# day with the snow line at 14,000 ft. state/home_gauge.json is {} and always
# has been, so nobody had ever entered a reading and the bundle carried no
# gauge value at all. The persona asks for exactly one personal detail and
# tells the model to rotate which one; when the stake's turn came up the model
# supplied a number for it, because a plausible number is what a language model
# produces where a number is expected.
#
# The prompt now states the absence in as many words, which is the fix. This is
# the backstop for the mornings it does not hold. A qualitative mention is
# fine and the voice needs it -- "the gauge is dry," "nothing in it" -- so only
# a FIGURE is caught.
_GAUGE_WORD = r"(?:rain gauge|snow stake|gauge|guage|stake)"
_FIGURE = (r"(?:\d+(?:\.\d+)?|a couple(?: of)?|a few|half an?|one|two|three|four|"
           r"five|six|seven|eight|nine|ten|eleven|twelve)")
# NOT a bare "in". It is the English preposition far more often than an inch
# abbreviation, and this persona writes in exactly the register that trips it:
# "nothing in the gauge, and I was up at 4 in the morning" matched, and the
# consequence of a match is a BLOCK. Any decimal near the gauge is caught by
# the unitless patterns below anyway, so dropping it costs almost nothing.
_INCHES = r'(?:"|inch(?:es)?\b)'

HOME_READING_PATTERNS = [
    re.compile(rf"\b{_GAUGE_WORD}\b[^.\n]{{0,60}}?({_FIGURE})\s*{_INCHES}", re.IGNORECASE),
    re.compile(rf"({_FIGURE})\s*{_INCHES}[^.\n]{{0,60}}?\b{_GAUGE_WORD}\b", re.IGNORECASE),
    # A liquid total needs no unit and the persona's own example has none:
    # "The gauge showed 0.12 overnight" is given as the model of a good
    # personal detail. A decimal point is required precisely so this does not
    # fire on the road numbers and elevations that surround it -- the 550, the
    # 501, 7,200 ft -- which are integers every time.
    re.compile(rf"\b{_GAUGE_WORD}\b[^.\n]{{0,30}}?(\d+\.\d+)", re.IGNORECASE),
    re.compile(rf"(\d+\.\d+)[^.\n]{{0,30}}?\b{_GAUGE_WORD}\b", re.IGNORECASE),
]


def _gauge_supports(gauge, stated):
    """Is `stated` a figure the hand-entered reading actually contains?"""
    if not gauge:
        return False
    try:
        value = float(stated)
    except (TypeError, ValueError):
        # A spelled number ("about three inches on the stake") is never treated
        # as supported. If a real reading is behind it, a person can say so in
        # ten seconds; the cost of the false positive is one glance.
        return False
    for key, v in gauge.items():
        if key == "for_date" or v is None:
            continue
        try:
            if abs(float(v) - value) < 0.05:
                return True
        except (TypeError, ValueError):
            continue
    return False


def unsupported_home_reading(bundle, text):
    """The offending phrase, or None. See HOME_READING_PATTERNS above."""
    for pattern in HOME_READING_PATTERNS:
        m = pattern.search(text or "")
        if not m:
            continue
        if _gauge_supports(bundle.get("home_gauge"), m.group(1)):
            continue
        return m.group(0).strip()
    return None


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

    stray = unsupported_home_reading(bundle, draft_text)
    if stray:
        escalate(BLOCK,
                 f"draft attributes a reading to the gauge or stake ({stray!r}) "
                 "that no hand-entered observation supports; there is nothing "
                 "in state/home_gauge.json for this date")

    # Road status without a road-status source.
    if not bundle.get("roads"):
        stated, road_why = road_status_claim(draft_text)
        if stated:
            escalate(BLOCK, f"draft {road_why} ({stated!r}) with no live CDOT "
                            "data behind it -- forecast the roads and the "
                            "passes, link CDOT for status")

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

    if (bundle.get("snow_line") or {}).get("above_terrain"):
        stated = states_a_terrain_impossible_snow_line(draft_text)
        if stated:
            escalate(REVIEW,
                     f"states a snow line of {stated} ft on a day the derived "
                     "line sits above the passes, the Weminuche and everywhere "
                     "else anyone here goes; the post should say it is rain "
                     "everywhere including up high, rather than print a figure "
                     "for ground nobody stands on")

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


def states_a_terrain_impossible_snow_line(text):
    """An elevation figure at or above the terrain ceiling, next to "snow line".

    The range is read from snowline.TERRAIN_CEILING_FT rather than written out
    here. An earlier version hardcoded 13,000-19,999 to match a 13,000 ft
    ceiling, which is two copies of one number and therefore one lowering away
    from silently checking the wrong thing. That is the same defect that let
    publish._auto_title drift from its twin.

    Only meaningful on a day the bundle already flagged `above_terrain`. The
    prompt tells the model not to print a figure at all; this is the belt for
    those braces, and it catches the rounding case too, where a line computed
    just under the ceiling is written just over it. REVIEW rather than BLOCK:
    the figure is accurate, it is only useless, so a false positive costs one
    person one glance.
    """
    from . import snowline as _sl
    for m in re.finditer(r"\b(\d{1,2}),?(\d{3})\b", text or ""):
        value = int(m.group(1) + m.group(2))
        if not (_sl.TERRAIN_CEILING_FT <= value <= 20000):
            continue
        near = (text[max(0, m.start() - 60):m.end() + 60]).lower()
        if "snow line" in near or "snowline" in near or "snow-line" in near:
            return m.group(0)
    return None


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
        "flagged: you have weather data, not road data, for the passes and "
        "equally for the 501, the 240 and the pavement in town. Never write "
        "that a road IS dry, clear, icy, open or closed, and never write the "
        "adjective on its own either -- 'dry roads', 'wet pavement', 'clear "
        "conditions' are the same claim with the verb left out. Forecast it "
        "instead, in the future or conditional, and point at CDOT for the "
        "status. 'Coal Bank should stay dry through the morning' and \"I'd "
        "expect wet pavement by the afternoon commute\" are right. "
        "'The passes are dry' and 'Dry roads for the bus run' are not.\n\n"
        "On your own gauge or snow stake specifically, if that is what was "
        "flagged: there is no reading from either one today and you did not "
        "measure anything. Keep your one personal detail, but make it "
        "something you saw rather than something you measured. No inch figure "
        "for the stake, no total for the gauge.\n\n"
        "Return only the post."
    )
