"""
Orchestrator: fetch conditions -> generate caption + card data -> render the
image -> post it (or dry-run it). This is the entry point the GitHub Actions
workflow calls.

Scheduling note: the workflow runs this HOURLY (every hour, all day, every
day) rather than at two hardcoded UTC cron times. That's deliberate, not
sloppy -- GitHub Actions cron is fixed in UTC, but "7am and 2pm" is a
Mountain Time promise, and Mountain Time flips between MST and MDT twice a
year. A fixed UTC cron would silently post an hour off from what David
actually wants every November and March until someone noticed and manually
re-edited the YAML. Instead, this script itself checks the current time in
America/Denver (which Python's zoneinfo handles DST for automatically) and
only actually posts inside the two target WINDOWS -- the other runs/day
are a few seconds of no-op. Cheap, and correct forever without maintenance.

WINDOWS, NOT EXACT HOURS (2026-09-27). The original gate was "only post if the
run happens to execute during the 7 o'clock (or 14 o'clock) hour". That is
correct only if the hourly cron is really hourly, and it is not: GitHub drops
and defers scheduled runs, and since late August this workflow has fired 5-7
times a day at arbitrary minutes. Between Aug 26 and Sep 26 only 17 of 64
slots posted, because most days no run happened to land in either hour. (The
forecaster hit the same wall and solved it the same way: scripts/wx/ledger.py.)
Now each slot owns a window of local hours, and the first surviving run inside
the window posts -- unless post_history.json says that slot already went out
today, which is what makes a wide window safe (four runs in a four hour window
must not be four posts). A run that dies before posting records nothing, so the
next run in the window retries.
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_conditions
import generate_post_text
import render_card
import post_to_facebook
import post_history

TIMEZONE = ZoneInfo("America/Denver")
SLOT_HOURS = {7: "morning", 14: "afternoon"}   # the nominal hours, kept for docs and tests
# [start, end) in local hours. Morning is 7:00-10:59, afternoon 14:00-17:59: late enough
# to survive a bad day for the scheduler, early enough that "this morning" is still true.
SLOT_WINDOWS = {"morning": (7, 11), "afternoon": (14, 18)}


def slot_for_hour(hour):
    """The slot whose window contains this local hour, or None."""
    for slot, (lo, hi) in SLOT_WINDOWS.items():
        if lo <= hour < hi:
            return slot
    return None


def slot_already_posted(slot, now, history=None):
    """True if a routine ("daily") post for this slot has already gone out on this
    Denver calendar date. post_history stores posted_at in whatever zone the runner
    used (UTC on Actions), so every entry is converted to Denver before comparing.
    Emergency alerts never count: they are not the daily card."""
    history = history if history is not None else post_history.load_history()
    today = now.astimezone(TIMEZONE).date()
    for p in history.get("posts", []):
        if not isinstance(p, dict):
            continue
        if p.get("slot") != slot or p.get("post_type", "daily") != "daily":
            continue
        try:
            when = datetime.fromisoformat(p["posted_at"])
        except (KeyError, TypeError, ValueError):
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=TIMEZONE)
        if when.astimezone(TIMEZONE).date() == today:
            return True
    return False


def determine_slot(now=None, history=None):
    """Returns "morning", "afternoon", or None (outside both windows, or that slot
    already posted today). FORCE_SLOT env var (or a CLI arg) bypasses the clock check
    and the already-posted check entirely -- used for manual workflow_dispatch test runs."""
    forced = os.environ.get("FORCE_SLOT")
    if len(sys.argv) > 1 and sys.argv[1] in ("morning", "afternoon"):
        forced = sys.argv[1]
    if forced in ("morning", "afternoon"):
        print(f"FORCE_SLOT={forced} -- skipping the clock check.")
        return forced

    now = now or datetime.now(TIMEZONE)
    slot = slot_for_hour(now.hour)
    if slot is None:
        windows = ", ".join(f"{k} {lo}:00-{hi}:00" for k, (lo, hi) in SLOT_WINDOWS.items())
        print(f"Current time in America/Denver is {now.strftime('%Y-%m-%d %H:%M %Z')} "
              f"-- outside both posting windows ({windows} local). Exiting without posting.")
        return None
    if slot_already_posted(slot, now, history):
        print(f"{now.strftime('%Y-%m-%d %H:%M %Z')}: the {slot} post already went out today. "
              "Exiting without posting.")
        return None
    return slot


def main():
    now = datetime.now(TIMEZONE)
    slot = determine_slot(now)
    if slot is None:
        return 0

    print(f"=== GoVallecito daily post: {slot} slot, {now.strftime('%Y-%m-%d %H:%M %Z')} ===")

    # Testing-only override, mirrors FORCE_SLOT's pattern above. See
    # generate_post_text._try_build_featured_image's docstring for exactly
    # what this does and doesn't bypass -- it does not manufacture seasonal
    # content for dates outside the almanac's existing entries.
    force_grounded_day = (os.environ.get("FORCE_GROUNDED_DAY") or "false").strip().lower() == "true"
    if force_grounded_day:
        print("FORCE_GROUNDED_DAY=true -- bypassing the seasonal-post interval gate (testing only).")

    print("Fetching conditions...")
    conditions = fetch_conditions.fetch_all()
    for key in ("weather", "streamflow", "lake_level", "fire"):
        status = "OK" if conditions.get(key) else "MISSING"
        print(f"  {key}: {status} -> {conditions.get(key)}")

    os.makedirs("output", exist_ok=True)

    print("Generating post text + card data...")
    post = generate_post_text.build_post(
        conditions, slot, dt=now,
        image_dest_path=os.path.join("output", "featured_image.jpg"),
        force_grounded_day=force_grounded_day,
    )
    print(f"  meta: {post['meta']}")

    image_path = os.path.join("output", "card.png")
    render_card.render_card(post["card_data"], image_path)
    print(f"Rendered card -> {image_path}")

    print("Posting...")
    result = post_to_facebook.post_photo(image_path, post["caption"])
    print(f"Done. Result: {result}")

    # Only log to post_history when something real actually went out --
    # a dry run has no real post_id and nothing for check_engagement.py to
    # look up later.
    #
    # "post_id" (the {page-id}_{post-id} composite Facebook uses for the
    # actual page post) is checked BEFORE "id" (the underlying photo
    # object's own id) -- Facebook's Graph API docs say engagement queries
    # (likes/comments/shares) should target the page-post id, not the photo
    # id, and the /{page-id}/photos endpoint's response includes both. Using
    # "id" first meant every live post was quietly logged under the wrong
    # object id, which check_engagement.py would then query engagement for.
    post_id = result.get("post_id") or result.get("id")
    if result.get("dry_run"):
        pass  # nothing to log for a dry run -- no real post_id, nothing to check engagement on later
    elif post_id:
        post_history.record_post(post_id, now.astimezone().isoformat(), slot, post["meta"])
        print(f"Logged to state/post_history.json (post_id={post_id})")
    else:
        # A live post that "succeeded" but returned neither post_id nor id
        # would otherwise vanish here with zero record and nothing in the
        # log calling that out -- a real public post that's silently never
        # tracked or checked for engagement. Make it loud instead.
        print("WARNING: a live post appears to have succeeded but the response had "
              f"no post_id/id to log (result={result}). This post will NOT be "
              "tracked in post_history.json or checked for engagement -- "
              "investigate the Graph API response shape.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
