"""
Turns fetched conditions into (1) the Facebook caption text and (2) the row
+ optional featured-image data render_card.py needs -- all built from the
same conditions dict so the words and the picture can never drift apart.

Implements docs/daily-post-template-style-guide.md. Short version: fixed
section order and icon mapping every single time, real numbers or an honest
omission -- never a guessed number, never yesterday's number relabeled as
today's.

Two things layered on top of the original design:

1. "Grounded" seasonal posts. On a rotating cadence (roughly once or twice a
   week, per the style guide's own "situational line" allowance), if
   today's date falls inside one of the researched windows in
   config/seasonal_almanac.json, the post tries to pull a real, safely-
   licensed photo from Wikimedia Commons (see fetch_image.py) and use the
   almanac's cited fact as the post's situational line. This only happens
   when BOTH a matching almanac entry AND a usable photo are available --
   "when applicable," not forced. A safety-relevant wildfire note (from
   fire_status.json) always outranks a seasonal fact for that one slot, per
   the style guide's own stated priority.

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

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALMANAC_PATH = os.path.join(REPO_ROOT, "config", "seasonal_almanac.json")
PREFERENCES_PATH = os.path.join(REPO_ROOT, "state", "content_preferences.json")

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
    return truncated.rstrip(",;: ") + "…"


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


def _is_grounded_day(dt, slot):
    # Restricted to one slot so a grounded day doesn't hand the same
    # seasonal photo/fact to both the morning and afternoon posts.
    if slot != "morning":
        return False
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


def _try_build_featured_image(dt, slot, image_dest_path):
    """Returns a featured_image dict for render_card.py, or None if today
    isn't a grounded day, no almanac entry matches, no safely-licensed
    photo could be found, or the matching entry is missing a required
    field -- any of which just means "no bonus photo today," not an
    error."""
    if not _is_grounded_day(dt, slot):
        return None
    entry = _matching_almanac_entry(dt)
    if not entry:
        return None

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
    }


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


def build_post(conditions, slot, dt=None, image_dest_path=None):
    """conditions: the dict from fetch_conditions.fetch_all().
    slot: "morning" or "afternoon".
    image_dest_path: where to save a featured photo if one gets used
    (defaults to output/featured_image.jpg next to card.png).
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
        caption_lines.append("💧 Lake level: data delayed — check govallecito.com")

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
        caption_lines.append("🌡️ Weather: data delayed — check govallecito.com")

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
    if streamflow and streamflow.get("cfs") is not None:
        caption_lines.append(f"🌊 Streamflow: {streamflow['cfs']:.0f} cfs (Vallecito Creek)")
        rows.append({
            "icon": "wave",
            "label": "STREAMFLOW",
            "value": f"{streamflow['cfs']:.0f} cfs (Vallecito Creek)",
            "badge": LAKE_2,
            "icon_color": WHITE,
        })
    # if streamflow is None: omit entirely -- we can't honestly say
    # "delayed" when we don't actually know that's why our fetch came back
    # empty.

    # -- optional situational line: safety (nearby wildfire) always wins
    # over a seasonal fact, per the style guide's own stated priority ------
    nearby = (fire or {}).get("nearby_wildfires") or {}
    featured_image = None
    if nearby.get("count", 0) > 0 and nearby.get("note"):
        caption_lines.append(f"🚨 {_condense(nearby['note'], SAFETY_NOTE_CHAR_BUDGET)}")
    else:
        featured_image = _try_build_featured_image(dt, slot, image_dest_path)
        if featured_image:
            caption_lines.append(
                f"🌿 {featured_image['_fact_for_caption']} (source: {featured_image['_source_name']})"
            )

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
