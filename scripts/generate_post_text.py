"""
Turns fetched conditions into (1) the Facebook caption text and (2) the row
+ optional featured-image data render_card.py needs -- all built from the
same conditions dict so the words and the picture can never drift apart.

Implements docs/daily-post-template-style-guide.md. Short version: fixed
section order and icon mapping every single time, real numbers or an honest
omission -- never a guessed number, never yesterday's number relabeled as
today's.

Two things layered on top of the original design:

1. "Grounded" content. On a rotating cadence (roughly once or twice a week,
   per the style guide's own "situational line" allowance), the post's one
   situational-line slot can carry one of three kinds of enrichment content
   instead of just the routine data rows -- see _try_build_grounded_content:
     a. The original (2026-07-22) seasonal almanac fact + a real,
        safely-licensed Wikimedia Commons photo (config/seasonal_almanac.json,
        fetch_image.py), rendered as its own dedicated photo band. Only
        happens when BOTH a matching almanac entry AND a usable photo are
        available -- "when applicable," not forced.
     b. Added 2026-07-26: a fishing-report spotlight, built from David's own
        Worker's real, weekly-updated fishing report (see
        fetch_conditions.fetch_fishing_report()). Caption-only, no photo.
     c. Added 2026-07-26: an evergreen site-section spotlight
        (config/site_spotlights.json) -- stories, webcams, the business
        directory, trail guide, etc. Also caption-only. Since this one has
        no live dependency and no date-range gate, it's the guaranteed-
        available fallback if the other two aren't (almanac's window
        doesn't match today, or the fishing-report fetch fails).
   Whichever of the three actually produces content wins a deterministic
   day-of-year rotation among whichever candidates are eligible that day --
   see _try_build_grounded_content's own docstring for exactly how. A
   safety-relevant wildfire note (sourced from David's Worker as of the
   2026-07-24 data-source-consolidation change, not the historical
   config/fire_status.json this comment used to reference) always outranks
   any of the three grounded-content kinds for that one slot, per the style
   guide's own stated priority.

2. Gentle, data-gated learning. If state/content_preferences.json exists
   (written by scripts/check_engagement.py from real engagement data), hook
   line selection becomes a soft-weighted random choice instead of pure
   rotation -- but ONLY for hooks that already have enough samples
   (MIN_SAMPLES_FOR_WEIGHTING) to mean anything. Below that, it's the same
   deterministic day-of-year rotation as before. This is deliberately not
   "always pick the best-scoring hook" -- that would defeat the style
   guide's own point of rotating hooks so posts don't feel copy-pasted, and
   with a brand new page, "best-scoring" from 3 data points isn't a real
   signal anyway.
"""

import json
import os
import random
from datetime import datetime

from render_card import MINT, LAKE, WHITE, INFO, DANGER, WARN, LAKE_2
import fetch_image
import fetch_conditions

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALMANAC_PATH = os.path.join(REPO_ROOT, "config", "seasonal_almanac.json")
SITE_SPOTLIGHTS_PATH = os.path.join(REPO_ROOT, "config", "site_spotlights.json")
PREFERENCES_PATH = os.path.join(REPO_ROOT, "state", "content_preferences.json")
DAILY_POST_STATE_PATH = os.path.join(REPO_ROOT, "state", "daily_post_state.json")

MIN_SAMPLES_FOR_WEIGHTING = 15
GROUNDED_POST_INTERVAL_DEFAULT = 4  # roughly 1.75x/week; see _grounded_interval()
GROUNDED_POST_INTERVAL_MIN = 3      # floor: ~2.3x/week, never more frequent than this
GROUNDED_POST_INTERVAL_MAX = 6      # ceiling: ~1.2x/week, never rarer than this

MORNING_HOOKS = [
    "Good morning, Vallecito.",
    "Rise and shine, lake people.",
    "Here's the morning read.",
    "Coffee's on — here's today's conditions.",
    "Morning check-in from the lake.",
]

AFTERNOON_HOOKS = [
    "Afternoon at the lake.",
    "Here's where things stand.",
    "Midday conditions check.",
    "Afternoon update, Vallecito.",
]

HASHTAG_CORE = "#VallecitoLake #KnowBeforeYouGo #SanJuanMountains"
SLOT_HASHTAG = {"morning": "#MorningReport", "afternoon": "#AfternoonUpdate"}

# Character budgets below are empirically measured against render_card.py's
# actual fonts/margins (the row-value font and the photo-band fact/headline
# fonts) -- each is the longest a string can be while still GUARANTEED to
# fit the existing card layout (2 lines for row values and the photo-band
# headline, 3 lines for the photo-band fact), with a safety margin below the
# raw measurement. The rule behind all of them: sacrifice length, not
# layout -- text is always shortened to fit the card as it exists today
# rather than the card ever growing to fit the text, and the SAME shortened
# text is used in both the caption and the image so the two can never show
# different information.
ROW_VALUE_CHAR_BUDGET = 75
SAFETY_NOTE_CHAR_BUDGET = 140
ALMANAC_FACT_CHAR_BUDGET = 235
ALMANAC_HEADLINE_CHAR_BUDGET = 80

# Budgets for the two new grounded-content kinds added 2026-07-26 (see
# _try_build_grounded_content). Both are CAPTION-ONLY, same rendering
# treatment as the wildfire situational note above (no card row, no photo
# band) -- captions don't have a hard pixel-overflow failure mode the way
# the rendered image does, but everything in this file gets a real budget
# regardless, same "never leave a length undefined" discipline as
# everywhere else here. The link itself is never condensed away, only the
# descriptive text in front of it -- same rule as every sign-off link in
# this file.
FISHING_REPORT_CHAR_BUDGET = 160
SITE_SPOTLIGHT_BLURB_CHAR_BUDGET = 180


def _condense(text, max_chars):
    """Shortens text to fit within max_chars, breaking on a word boundary
    and adding an ellipsis, rather than leaving it to be truncated later --
    silently, or differently -- by whatever happens to render it. Condensing
    HERE, once, before the text branches into both the caption and the card
    row/photo band, is what guarantees the two can never disagree."""
    if not text or len(text) <= max_chars:
        return text
    truncated = text[:max_chars - 1]
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    # Also strip a trailing "." (added 2026-07-26, noticed while building the
    # fishing-report spotlight, which happens to append more text right after
    # this function's own "…" -- a truncation landing right after a real
    # sentence's period previously produced a double-punctuation "…." or
    # ".…" artifact. Applies to every caller, not just the new one: a
    # condensed value is already mid-thought and gets an ellipsis regardless,
    # so it should never have also been allowed to look like a complete
    # sentence via a leftover period.
    return truncated.rstrip(",;:. ") + "…"


def _lowercase_first(s):
    if not s:
        return s
    first_word = s.split(" ", 1)[0]
    if len(first_word) > 1 and first_word.isupper():
        # Leave acronyms (e.g. "NOAA") alone rather than mangling them into
        # "nOAA" -- only lowercase a normal capitalized first letter.
        return s
    return s[0].lower() + s[1:]


def _load_json_safe(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _load_daily_post_state():
    """See _decide_wildfire_situational_line()'s docstring for what this
    tracks and why. Missing/corrupt file -> the safe "nothing known yet"
    default, same fail-open behavior as _load_json_safe above -- worst
    case a fire that's actually already been reported gets treated as
    "new" one extra time, not a crash."""
    return _load_json_safe(DAILY_POST_STATE_PATH, {"nearby_wildfires": {"last_known_count": 0}})


def _save_daily_post_state(state):
    """Mirrors post_history.py's save_history(): write-to-temp-then-
    os.replace so a run that dies mid-write can never leave this file
    half-written/corrupt for the next run to trip over. The GitHub Actions
    workflow is responsible for committing this file back to the repo when
    it changes (see .github/workflows/daily-post.yml) -- same split of
    responsibilities as post_history.py's own module docstring describes."""
    try:
        os.makedirs(os.path.dirname(DAILY_POST_STATE_PATH), exist_ok=True)
        tmp_path = DAILY_POST_STATE_PATH + f".tmp-{os.getpid()}"
        with open(tmp_path, "w") as f:
            json.dump(state, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, DAILY_POST_STATE_PATH)
    except Exception as exc:
        print(f"[generate_post_text] failed to save {DAILY_POST_STATE_PATH}: {exc}")


def _pick_hook(slot, dt):
    """Weighted-if-we-have-data, otherwise deterministic day-of-year
    rotation. See module docstring for why it's gated on sample size."""
    bank = MORNING_HOOKS if slot == "morning" else AFTERNOON_HOOKS
    prefs = _load_json_safe(PREFERENCES_PATH, {})
    sample_counts = prefs.get("sample_counts", {}).get("hooks", {})
    ready = all(sample_counts.get(h, 0) >= MIN_SAMPLES_FOR_WEIGHTING for h in bank)

    if ready:
        weights_dict = prefs.get("hook_weights", {}).get(slot, {})
        weights = [weights_dict.get(h, 1.0) for h in bank]
        return random.choices(bank, weights=weights, k=1)[0]

    return bank[dt.timetuple().tm_yday % len(bank)]


def _grounded_interval():
    """How many days between 'grounded' seasonal posts. Bounded so learning
    can nudge it but never turn it into either spam or never-happens --
    the style guide's own "once or twice a week, never replacing the core
    data" rule is a hard ceiling on frequency, not a suggestion."""
    prefs = _load_json_safe(PREFERENCES_PATH, {})
    try:
        interval = int(prefs.get("grounded_post_interval_days", GROUNDED_POST_INTERVAL_DEFAULT))
    except (TypeError, ValueError):
        interval = GROUNDED_POST_INTERVAL_DEFAULT
    return max(GROUNDED_POST_INTERVAL_MIN, min(GROUNDED_POST_INTERVAL_MAX, interval))


def _is_grounded_day(dt, slot, force=False):
    # Restricted to one slot so a grounded day doesn't hand the same
    # seasonal photo/fact to both the morning and afternoon posts -- this
    # restriction still applies even when force=True; forcing overrides the
    # interval gate below, not the one-slot-per-day rule.
    if slot != "morning":
        return False
    if force:
        return True
    return dt.timetuple().tm_yday % _grounded_interval() == 0


def _matching_almanac_entry(dt):
    """MM-DD string comparison. Handles ranges that wrap across New Year's
    (start > end, e.g. bald_eagle_winter's 12-01..02-28) via OR logic
    instead of the AND logic that works for same-year ranges."""
    def _in_range(entry):
        start, end = entry.get("date_start", ""), entry.get("date_end", "")
        if start <= end:
            return start <= today_md <= end
        return today_md >= start or today_md <= end

    almanac = _load_json_safe(ALMANAC_PATH, {"entries": []})
    today_md = dt.strftime("%m-%d")
    matches = [e for e in almanac.get("entries", []) if _in_range(e)]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    # Deterministic tie-break instead of random.choice -- the same day
    # should always resolve to the same entry across multiple calls/slots.
    ordered = sorted(matches, key=lambda e: e.get("id", ""))
    return ordered[dt.timetuple().tm_yday % len(ordered)]


def _build_almanac_content(entry, image_dest_path):
    """The original (2026-07-22, photo-crop-fixed 2026-07-24/07-26) grounded
    content: a seasonal almanac fact + a real, safely-licensed Commons photo,
    rendered as render_card.py's dedicated photo band (not a caption-only
    line the way the other two grounded-content kinds below are). Assumes
    the caller has already confirmed `entry` matches today's date --
    kept as a separate function (rather than folded into the dispatcher)
    purely so it reads the same as the other two _build_*_content functions
    below it.

    Returns None (not an error) if the entry is missing a required field or
    no usable photo could be found -- either just means "no bonus photo
    today," and the dispatcher below falls through to the next candidate
    rather than giving up on grounded content entirely."""
    required = ("id", "headline", "fact", "source_name", "commons_category")
    missing = [k for k in required if not entry.get(k)]
    if missing:
        print(f"[generate_post_text] almanac entry matched today but is missing required field(s) {missing}, skipping")
        return None

    image = fetch_image.get_seasonal_image(entry["commons_category"], image_dest_path)
    if not image:
        print(f"[generate_post_text] almanac entry '{entry['id']}' matched today but no usable photo found")
        return None

    headline = _condense(entry["headline"], ALMANAC_HEADLINE_CHAR_BUDGET)
    fact = _condense(entry["fact"], ALMANAC_FACT_CHAR_BUDGET)

    return {
        "kind": "almanac",
        "_meta_id": entry["id"],
        "featured_image": {
            "path": image["local_path"],
            "headline": headline,
            "fact": fact,
            "credit_text": "Photo: Wikimedia Commons, public domain",
            # kept alongside for the caption + for post_history logging -- the
            # same (possibly condensed) headline/fact used in the image above,
            # so the caption can never show more than the image does.
            "_entry_id": entry["id"],
            "_fact_for_caption": fact,
            "_source_name": entry["source_name"],
        },
    }


def _build_fishing_report_content():
    """Second grounded-content kind, added 2026-07-26: a caption-only
    spotlight built from David's own Worker's real, weekly-updated fishing
    report (see fetch_conditions.fetch_fishing_report()). Unlike the
    almanac path above, there's no photo/card-image treatment here -- same
    caption-only pattern as the wildfire situational note in build_post()
    below. Returns None (not an error) if the Worker fetch fails or comes
    back with no usable summary -- the dispatcher just tries the next
    candidate."""
    report = fetch_conditions.fetch_fishing_report()
    if not report:
        return None
    text = _condense(report["summary"], FISHING_REPORT_CHAR_BUDGET)
    return {
        "kind": "fishing_report",
        "_meta_id": "fishing_report",
        "caption_text": f"{text} Full report → govallecito.com/fishing-report",
    }


def _pick_site_spotlight(dt):
    """Deterministic day-of-year rotation through config/site_spotlights.json
    -- same tie-break style as _matching_almanac_entry and _pick_hook's
    fallback, so the same day always resolves to the same entry no matter
    how many times this is called. Returns None only if the config is
    missing/empty (fails open, same as every other _load_json_safe use in
    this file) -- in practice this file always has entries, making this the
    "there's always something to say" bottom rung of the rotation."""
    spotlights = _load_json_safe(SITE_SPOTLIGHTS_PATH, {"entries": []}).get("entries", [])
    if not spotlights:
        return None
    return spotlights[dt.timetuple().tm_yday % len(spotlights)]


def _build_site_spotlight_content(dt):
    """Third grounded-content kind, added 2026-07-26: an evergreen spotlight
    on one of govallecito.com's own site sections or story pages (see
    config/site_spotlights.json -- same hand-curated, verified-against-the-
    real-page discipline as seasonal_almanac.json, just not date-gated).
    Caption-only, same as the fishing-report kind above."""
    entry = _pick_site_spotlight(dt)
    if not entry:
        return None
    required = ("id", "headline", "blurb", "url")
    missing = [k for k in required if not entry.get(k)]
    if missing:
        print(f"[generate_post_text] site spotlight entry matched but missing required field(s) {missing}, skipping")
        return None
    blurb = _condense(entry["blurb"], SITE_SPOTLIGHT_BLURB_CHAR_BUDGET)
    return {
        "kind": "site_spotlight",
        "_meta_id": entry["id"],
        "caption_text": f"{entry['headline']} {blurb} → {entry['url']}",
    }


def _try_build_grounded_content(dt, slot, image_dest_path, force_grounded_day=False):
    """Dispatcher for ALL grounded/situational content, generalized
    2026-07-26 from the original almanac-only _try_build_featured_image
    (David asked for the bot to also spotlight site sections -- stories,
    fishing report, webcams, etc. -- not just wildlife facts). Returns a
    dict with a "kind" key ("almanac" / "fishing_report" / "site_spotlight")
    build_post() below uses to decide how to render it, or None if today
    isn't a grounded day or nothing was available from any candidate.

    force_grounded_day bypasses the interval gate (testing only -- see
    FORCE_GROUNDED_DAY in daily-post.yml) but does NOT bypass the almanac's
    own date-range match: forcing on a date outside all 4 current almanac
    entries' windows still won't produce almanac content, though it can
    still produce a fishing-report or site-spotlight result, since neither
    of those is date-gated. This flag proves the pipeline works, it doesn't
    manufacture seasonal content that doesn't exist yet.

    Rotation: almanac (if a window matches today) is one candidate among
    three, not an automatic first choice -- ordered by a deterministic
    day-of-year rotation (same "no true randomness, same day always
    resolves the same way" rule as everywhere else in this file) so that on
    days when an almanac entry DOES match, it doesn't always crowd out the
    other two. Whichever candidate is tried first that actually succeeds
    wins; a candidate that returns None (Worker unreachable for the fishing
    report, no safely-licensed photo for the almanac entry, etc.) just
    means the dispatcher tries the next one -- site_spotlight is a static
    local config with no live dependency, so it's the guaranteed-available
    bottom rung if both other candidates fail."""
    if not _is_grounded_day(dt, slot, force=force_grounded_day):
        return None

    almanac_entry = _matching_almanac_entry(dt)
    eligible = (["almanac"] if almanac_entry else []) + ["fishing_report", "site_spotlight"]
    start = dt.timetuple().tm_yday % len(eligible)
    ordered = eligible[start:] + eligible[:start]

    for kind in ordered:
        if kind == "almanac":
            result = _build_almanac_content(almanac_entry, image_dest_path)
        elif kind == "fishing_report":
            result = _build_fishing_report_content()
        else:
            result = _build_site_spotlight_content(dt)
        if result:
            return result
    return None


def _decide_wildfire_situational_line(fire):
    """Decides whether today's post should lead its one situational-line
    slot with the nearby-wildfire safety note (as opposed to letting a
    seasonal photo take that slot instead), and updates
    state/daily_post_state.json to match. See the README's change log for
    the full story (dated 2026-07-24); short version below.

    Before this change, the safety note was shown on ANY post where a
    wildfire sat within 50mi -- no memory of whether a previous post had
    already said so. Once fire/wildfire data started coming from David's
    own Worker (2026-07-24's Tier-2 change) instead of a hand-maintained
    config file that in practice never had a real entry, this went from
    effectively dormant to firing on every single post for as long as any
    wildfire stayed within range -- weeks, for a slow-burning one -- and
    since the card has only one situational-line slot, that also silently
    shut out the seasonal-photo feature the entire time. That's the same
    fact being repeated, not new information each time.

    A genuinely NEW wildfire report should still always win that slot --
    unchanged, safety-first behavior. "New" is judged the same way
    check_emergency.py's own _check_fire_escalation() already judges it
    for the immediate-alert path: the nearby-wildfire COUNT going up
    versus the last count THIS state file recorded (a separate file from
    check_emergency.py's own state -- "has a routine daily post already
    told the public about this" and "has an emergency alert already fired
    for this" are answered by two different, independently-scheduled
    workflows, and conflating them would couple two features that should
    be free to evolve independently). A count decrease, or an unchanged
    count with only the descriptive note text differing (e.g. a
    containment percentage ticking up), is NOT treated as new -- exactly
    David's own framing: a status update "should not block seasonal photo
    posting."

    Returns (should_show_note, note_text_or_None). Always saves state to
    the CURRENT count before returning regardless of the decision, so the
    next run's comparison is against reality rather than a stale value --
    same update-every-run behavior as _check_fire_escalation().
    """
    nearby = (fire or {}).get("nearby_wildfires") or {}
    current_count = nearby.get("count", 0) or 0
    note = nearby.get("note")

    state = _load_daily_post_state()
    wildfire_state = state.setdefault("nearby_wildfires", {})
    last_known_count = wildfire_state.get("last_known_count", 0) or 0
    is_new_report = current_count > last_known_count
    show_note = bool(current_count > 0 and note and is_new_report)

    wildfire_state["last_known_count"] = current_count
    _save_daily_post_state(state)

    return show_note, (note if show_note else None)


def _fire_badge_color(fire):
    if not fire:
        return WARN
    try:
        stage = int(fire.get("stage", 0))
    except (TypeError, ValueError):
        stage = 0
    try:
        nearby_count = int((fire.get("nearby_wildfires") or {}).get("count", 0))
    except (TypeError, ValueError):
        nearby_count = 0
    return DANGER if (stage >= 2 or nearby_count > 0) else WARN


def build_post(conditions, slot, dt=None, image_dest_path=None, force_grounded_day=False):
    """conditions: the dict from fetch_conditions.fetch_all().
    slot: "morning" or "afternoon".
    image_dest_path: where to save a featured photo if one gets used
    (defaults to output/featured_image.jpg next to card.png).
    force_grounded_day: testing-only override, see _try_build_featured_image's
    docstring for exactly what it does and doesn't bypass.
    Returns {"caption": str, "card_data": dict, "meta": dict} -- "meta" is
    the bit main.py logs to state/post_history.json for the engagement loop.
    """
    dt = dt or datetime.now()
    image_dest_path = image_dest_path or os.path.join("output", "featured_image.jpg")

    weather = conditions.get("weather")
    streamflow = conditions.get("streamflow")
    lake = conditions.get("lake_level")
    fire = conditions.get("fire")

    hook = _pick_hook(slot, dt)
    weekday_date = dt.strftime("%A, %B %-d")

    caption_lines = [f"{weekday_date} — {_lowercase_first(hook)}", ""]
    rows = []

    # -- lake level --------------------------------------------------------
    if lake and lake.get("pct_full") is not None:
        elev_part = (
            f" (elev. {lake['elevation_ft']:,.0f} ft, full pool is 7,665 ft)"
            if lake.get("elevation_ft") is not None
            else ""
        )
        caption_lines.append(f"💧 Lake: {lake['pct_full']}% of full pool{elev_part}")
        rows.append({
            "icon": "droplet",
            "label": "LAKE LEVEL",
            "value": f"{lake['pct_full']}% of full pool" + (
                f"  ·  elev. {lake['elevation_ft']:,.0f} ft" if lake.get("elevation_ft") is not None else ""
            ),
            "badge": MINT,
            "icon_color": LAKE,
        })
    else:
        # The style guide's general rule is "say data delayed... don't
        # carry yesterday's number forward silently" -- lake level has no
        # explicit "omit if missing" exception the way streamflow does
        # (see the streamflow block below), so a missing/incomplete
        # reading should say so rather than vanish silently.
        #
        # The card row mirrors the caption for the same reason fire status
        # already did (see below): if the caption says "data delayed" but
        # the card just drops the row, the two disagree about what happened
        # -- exactly the divergence this whole feature exists to prevent.
        caption_lines.append("💧 Lake level: data delayed — check govallecito.com")
        rows.append({
            "icon": "droplet",
            "label": "LAKE LEVEL",
            "value": "Data delayed — check govallecito.com",
            "badge": WARN,
            "icon_color": LAKE,
        })

    # -- weather -------------------------------------------------------------
    if weather and weather.get("current_f") is not None:
        high = f", headed to a high of {weather['high_f']}°" if weather.get("high_f") is not None else ""
        forecast_txt = f" {weather['short_forecast']}." if weather.get("short_forecast") else ""
        caption_lines.append(f"🌡️ {weather['current_f']}°F now{high}.{forecast_txt}".replace("..", "."))
        rows.append({
            "icon": "thermo",
            "label": "WEATHER",
            "value": f"{weather['current_f']}°F now"
                     + (f" · high {weather['high_f']}°" if weather.get("high_f") is not None else "")
                     + (f", {weather['short_forecast'].lower()}" if weather.get("short_forecast") else ""),
            "badge": INFO,
            "icon_color": WHITE,
        })
    else:
        # Same reasoning as the lake-level branch above: mirror the
        # caption's "data delayed" in the card row instead of silently
        # dropping the row, so the two can't disagree.
        caption_lines.append("🌡️ Weather: data delayed — check govallecito.com")
        rows.append({
            "icon": "thermo",
            "label": "WEATHER",
            "value": "Data delayed — check govallecito.com",
            "badge": WARN,
            "icon_color": WHITE,
        })

    # -- fire status (always shown if config loaded) ------------------------
    if fire:
        stage_label = fire.get("stage_label", "Fire restrictions")
        raw_summary = fire.get("restrictions_summary", "")
        # Condensed ONCE, combined with the label, since that combined
        # string is exactly what has to fit in the card row -- the caption
        # line then just adds the emoji on top of the same text, so caption
        # and image can never show different fire information.
        fire_value = _condense(f"{stage_label}: {raw_summary}", ROW_VALUE_CHAR_BUDGET)
        caption_lines.append(f"🔥 {fire_value}")
        rows.append({
            "icon": "flame",
            "label": "FIRE STATUS",
            "value": fire_value,
            "badge": _fire_badge_color(fire),
            "icon_color": WHITE,
            "flame_inner": (255, 224, 130),
        })
    else:
        caption_lines.append("🔥 Fire status: data delayed — check govallecito.com")
        rows.append({
            "icon": "flame",
            "label": "FIRE STATUS",
            "value": "Data delayed — check govallecito.com",
            "badge": WARN,
            "icon_color": WHITE,
            "flame_inner": (255, 224, 130),
        })

    # -- streamflow ----------------------------------------------------------
    # Wording depends on fetch_conditions.py's "combined" flag: normally
    # (Worker reachable) this is the combined Pine River + Vallecito Creek
    # figure -- the same one govallecito.com's own Fishing Report text uses
    # -- so it's labeled "combined inflow"; during a Worker outage the
    # fallback path only has the single Vallecito Creek USGS gauge, so it's
    # labeled the same way it always used to be. The number and the label
    # change together so the two can never disagree about what's actually
    # being measured.
    if streamflow and streamflow.get("cfs") is not None:
        flow_label = "cfs combined inflow" if streamflow.get("combined") else "cfs (Vallecito Creek)"
        caption_lines.append(f"🌊 Streamflow: {streamflow['cfs']:.0f} {flow_label}")
        rows.append({
            "icon": "wave",
            "label": "STREAMFLOW",
            "value": f"{streamflow['cfs']:.0f} {flow_label}",
            "badge": LAKE_2,
            "icon_color": WHITE,
        })
    # if streamflow is None: omit entirely -- we can't honestly say
    # "delayed" when we don't actually know that's why our fetch came back
    # empty.

    # -- optional situational line: a genuinely NEW wildfire report always
    # wins over grounded content, per the style guide's own stated safety-
    # first priority -- but see _decide_wildfire_situational_line()'s
    # docstring for why "new" is not the same test as "currently nonzero"
    # (an ongoing, already-known fire no longer monopolizes this slot on
    # every single post). Below that, grounded content is now one of three
    # kinds (added 2026-07-26 -- see _try_build_grounded_content): the
    # original seasonal-almanac photo, a fishing-report spotlight, or a
    # site-section spotlight -- exactly one caption-only emoji-prefixed line
    # for the latter two, matching the wildfire note's own caption-only
    # treatment; the almanac kind is the one exception that also gets a
    # dedicated photo band, unchanged from before this rewrite. ----------
    show_wildfire_note, wildfire_note_text = _decide_wildfire_situational_line(fire)
    featured_image = None
    grounded = None
    if show_wildfire_note:
        caption_lines.append(f"🚨 {_condense(wildfire_note_text, SAFETY_NOTE_CHAR_BUDGET)}")
    else:
        grounded = _try_build_grounded_content(dt, slot, image_dest_path, force_grounded_day=force_grounded_day)
        if grounded and grounded["kind"] == "almanac":
            featured_image = grounded["featured_image"]
            caption_lines.append(
                f"🌿 {featured_image['_fact_for_caption']} (source: {featured_image['_source_name']})"
            )
        elif grounded and grounded["kind"] == "fishing_report":
            caption_lines.append(f"🎣 {grounded['caption_text']}")
        elif grounded and grounded["kind"] == "site_spotlight":
            caption_lines.append(f"📍 {grounded['caption_text']}")

    # -- sign-off --------------------------------------------------------
    caption_lines.append("")
    caption_lines.append("Full conditions → govallecito.com")
    caption_lines.append(f"{HASHTAG_CORE} {SLOT_HASHTAG.get(slot, '')}".strip())

    caption = "\n".join(caption_lines)

    card_data = {
        "date_label": weekday_date.upper(),
        "hook_line": hook,
        "rows": rows,
        "footer_text": "govallecito.com",
    }
    if featured_image:
        card_data["featured_image"] = featured_image

    meta = {
        "hook_line": hook,
        "slot": slot,
        "had_image": bool(featured_image),
        "image_topic": featured_image["_entry_id"] if featured_image else None,
        # New 2026-07-26: which of the three grounded-content kinds (if any)
        # filled today's situational-line slot, and its specific entry id --
        # generalizes image_topic above (which only ever meant "almanac")
        # so check_engagement.py's learning loop can eventually compare
        # engagement across kinds, not just within almanac topics. None/None
        # when the wildfire note won the slot instead, or nothing was
        # available at all.
        "grounded_kind": grounded["kind"] if grounded else None,
        "grounded_id": grounded["_meta_id"] if grounded else None,
        "fire_stage": (fire or {}).get("stage"),
    }

    return {"caption": caption, "card_data": card_data, "meta": meta}


# =============================================================================
# Emergency alerts (flood / fire / evacuation / disaster) -- posted
# immediately by scripts/check_emergency.py, no scheduling wait, no
# manual-approval gate. See that file for how an alert is detected; this is
# just the "turn one into a post" half, kept in this file (not a separate
# module) because it reuses _condense(), the row-list structure, and the
# color imports already set up above -- it is NOT a parallel post-building
# system, it's the same one with a different row recipe.
# =============================================================================

ALERT_CATEGORY_DISPLAY = {
    "flood": {
        "emoji": "🌊",
        "row_label": "FLOOD ALERT",
        "hook": "Flood alert — Vallecito.",
        "hashtag": "#FloodSafety",
        "cta": "Follow local road-closure and evacuation guidance",
    },
    "fire": {
        "emoji": "🔥",
        "row_label": "FIRE ALERT",
        "hook": "Fire alert — Vallecito.",
        "hashtag": "#FireSafety",
        "cta": "Check current restrictions before any open flame",
    },
    "evacuation": {
        "emoji": "🚨",
        "row_label": "EVACUATION ALERT",
        "hook": "Evacuation alert — Vallecito.",
        "hashtag": "#EvacuationAlert",
        "cta": "Follow official evacuation guidance from local authorities",
    },
    "disaster": {
        "emoji": "🚨",
        "row_label": "EMERGENCY ALERT",
        "hook": "Emergency alert — Vallecito.",
        "hashtag": "#SafetyAlert",
        "cta": "Follow official guidance from local authorities",
    },
}


def build_alert_post(conditions, alert, dt=None):
    """Builds a safety-priority-variant post for a flood/fire/evacuation/
    disaster alert -- reuses the EXACT SAME card renderer, row structure,
    fonts, and condensing rules as build_post()'s routine daily posts (the
    "make posts always stay within existing layout" rule applies to every
    post this bot makes, not just the scheduled ones). The only real
    difference from a routine post is which rows appear and in what order:
    the alert leads, everything else is brief supporting context, and there
    is deliberately no seasonal photo -- safety content only, matching the
    style guide's existing rule that safety always outranks a seasonal fact
    for that slot.

    alert: {"category", "headline", "description", "source_name",
    "source_url", ...} -- the normalized shape check_emergency.py produces,
    whether the alert came from the NWS feed, config/emergency_override.json,
    or a config/fire_status.json escalation. Unrecognized/missing category
    falls back to "disaster" (the generic catch-all framing) rather than
    crashing on a category typo in a hand-edited override file.
    """
    dt = dt or datetime.now()
    category = alert.get("category")
    if category not in ALERT_CATEGORY_DISPLAY:
        category = "disaster"
    display = ALERT_CATEGORY_DISPLAY[category]

    weather = conditions.get("weather")
    lake = conditions.get("lake_level")
    fire = conditions.get("fire")

    weekday_date = dt.strftime("%A, %B %-d")

    # Condensed ONCE, same pattern as every other free-text field in this
    # file -- the exact same string then appears in both the caption line
    # and the card row, so they can never show different alert information.
    raw_headline = alert.get("headline") or alert.get("event") or "Alert"
    description = alert.get("description") or ""
    combined = f"{raw_headline}: {description}" if description else raw_headline
    alert_value = _condense(combined, ROW_VALUE_CHAR_BUDGET)

    caption_lines = [f"{weekday_date} — {display['hook']}", ""]
    caption_lines.append(f"{display['emoji']} {alert_value}")

    rows = [{
        "icon": "alert",
        "label": display["row_label"],
        "value": alert_value,
        "badge": DANGER,
        "icon_color": WHITE,
    }]

    # -- brief supporting context: lake + weather, same fields/format as the
    # routine post's rows, just fewer of them (style guide: "4-6 lines of
    # actual content," and the alert itself is the point, not the context).
    if lake and lake.get("pct_full") is not None:
        lake_value = f"{lake['pct_full']}% of full pool"
        caption_lines.append(f"💧 Lake: {lake_value}")
        rows.append({
            "icon": "droplet",
            "label": "LAKE LEVEL",
            "value": lake_value,
            "badge": MINT,
            "icon_color": LAKE,
        })

    if weather and weather.get("current_f") is not None:
        high = f", high {weather['high_f']}°" if weather.get("high_f") is not None else ""
        weather_value = f"{weather['current_f']}°F now{high}"
        caption_lines.append(f"🌡️ {weather_value}.")
        rows.append({
            "icon": "thermo",
            "label": "WEATHER",
            "value": weather_value,
            "badge": INFO,
            "icon_color": WHITE,
        })

    # Skip the separate fire-status row when the alert itself IS a fire
    # alert -- the alert row above already says everything that row would,
    # and repeating it would burn one of the "4-6 lines" on a duplicate.
    if category != "fire" and fire:
        stage_label = fire.get("stage_label", "Fire restrictions")
        raw_summary = fire.get("restrictions_summary", "")
        fire_value = _condense(f"{stage_label}: {raw_summary}" if raw_summary else stage_label, ROW_VALUE_CHAR_BUDGET)
        caption_lines.append(f"🔥 {fire_value}")
        rows.append({
            "icon": "flame",
            "label": "FIRE STATUS",
            "value": fire_value,
            "badge": _fire_badge_color(fire),
            "icon_color": WHITE,
            "flame_inner": (255, 224, 130),
        })

    caption_lines.append("")
    if alert.get("source_name"):
        caption_lines.append(f"Source: {alert['source_name']}")
    caption_lines.append(f"{display['cta']} → govallecito.com")
    caption_lines.append(f"#VallecitoLake #KnowBeforeYouGo {display['hashtag']}")

    caption = "\n".join(caption_lines)

    card_data = {
        "date_label": weekday_date.upper(),
        "hook_line": display["hook"],
        "rows": rows,
        "footer_text": "govallecito.com",
    }

    meta = {
        "hook_line": display["hook"],
        "post_type": "emergency_alert",
        "alert_category": category,
        "alert_id": alert.get("id"),
        "had_image": False,
        "image_topic": None,
        "fire_stage": (fire or {}).get("stage"),
    }

    return {"caption": caption, "card_data": card_data, "meta": meta}
