"""
Looks back at posts that are at least 48 hours old, pulls their current
like/comment/share counts from the Graph API, and (gradually, gated on
sample size) turns that into state/content_preferences.json -- the weights
generate_post_text.py reads for hook-line selection and how often "grounded"
seasonal posts happen.

Run via .github/workflows/engagement-check.yml (daily). Can also be run by
hand: python scripts/check_engagement.py

*** NOT CONFIRMED LIVE *** same caveat as the rest of this repo: the Graph
API call's exact field syntax (likes.summary(true) etc.) is written from
long-stable, well-documented Graph API convention, not a live test call --
this sandbox can't reach graph.facebook.com any more than the others. Errors
per-post are caught and logged rather than crashing the whole run, so one
bad response doesn't block checking every other post.

On "learning": with a brand new page, don't expect this file to say
anything meaningful for a while. MIN_SAMPLES (15) per hook line, at roughly
one use per hook per week, is realistically a few months of real posting
before hook-level weighting activates at all. That's intentional -- see the
comments in generate_post_text.py for why guessing from 3 data points would
be worse than not guessing.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import post_history

GRAPH_API_VERSION = "v25.0"
MIN_HOURS_BEFORE_CHECK = 48
MIN_SAMPLES = 15
PREFERENCES_PATH = os.path.join(post_history.REPO_ROOT, "state", "content_preferences.json")

WEIGHT_FLOOR = 0.6
WEIGHT_CEILING = 1.6


def _hours_since(iso_timestamp):
    posted = datetime.fromisoformat(iso_timestamp)
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - posted).total_seconds() / 3600


def fetch_engagement(post_id, access_token):
    """Returns {"likes": N, "comments": N, "shares": N, "total": N} or None
    on failure."""
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{post_id}"
    params = {
        "fields": "likes.summary(true),comments.summary(true),shares",
    }
    # access_token goes in the Authorization header, NOT the URL query
    # string -- requests/urllib3 connection-level exception messages (DNS,
    # timeout, proxy failures) frequently embed the full attempted URL, so a
    # token passed as a query param can end up printed in cleartext in the
    # except-block log line below. post_to_facebook.py already avoids this
    # (it uses the POST body); Graph API documents Bearer-header auth as an
    # equally valid alternative to the query-param form for GET requests.
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=20)
        data = resp.json()
        if resp.status_code >= 400 or "error" in data:
            print(f"[fetch_engagement] {post_id}: API error -> {data.get('error')}")
            return None
        likes = data.get("likes", {}).get("summary", {}).get("total_count", 0)
        comments = data.get("comments", {}).get("summary", {}).get("total_count", 0)
        shares = data.get("shares", {}).get("count", 0)
        return {"likes": likes, "comments": comments, "shares": shares, "total": likes + comments + shares}
    except Exception as exc:
        print(f"[fetch_engagement] {post_id}: failed -> {exc}")
        return None


MAX_HOURS_BEFORE_GIVING_UP = 24 * 14  # ~2 weeks -- if a post's engagement still
                                       # can't be fetched by then (deleted post,
                                       # permissions change, bad post_id, etc.),
                                       # stop retrying forever and record it as
                                       # unavailable instead.


def update_pending_engagement(access_token):
    """Checks every unchecked post that's old enough, records what it finds.
    Returns the number of posts updated."""
    history = post_history.load_history()
    updated = 0
    for post in history["posts"]:
        try:
            # Explicit `is True` rather than plain truthiness -- a hand-edited
            # or otherwise corrupted history file could have this field as
            # the STRING "false", which Python treats as truthy and would
            # silently skip checking that post forever.
            if post.get("engagement_checked") is True:
                continue
            hours_old = _hours_since(post["posted_at"])
            if hours_old < MIN_HOURS_BEFORE_CHECK:
                continue
            engagement = fetch_engagement(post["post_id"], access_token)
            if engagement is None:
                if hours_old >= MAX_HOURS_BEFORE_GIVING_UP:
                    print(f"  {post['post_id']}: still unfetchable after {hours_old:.0f}h -- "
                          "giving up, recording as unavailable rather than retrying forever")
                    post["engagement"] = None
                    post["engagement_checked"] = True
                    post["engagement_checked_at"] = datetime.now(timezone.utc).isoformat()
                    post["engagement_unavailable"] = True
                    updated += 1
                else:
                    print(f"  {post['post_id']}: could not fetch engagement this run, will retry next run")
                continue
            post["engagement"] = engagement
            post["engagement_checked"] = True
            post["engagement_checked_at"] = datetime.now(timezone.utc).isoformat()
            updated += 1
            print(f"  {post['post_id']} ({post['posted_at']}): {engagement}")
        except Exception as exc:
            # One malformed record (missing/unparseable posted_at, missing
            # post_id, etc.) must not take down every other post's check --
            # this loop used to have no per-post isolation at all, so a
            # single bad row permanently halted engagement-checking for the
            # entire history, every run.
            print(f"  [update_pending_engagement] skipping malformed post record "
                  f"({post.get('post_id', '<no post_id>')}): {exc}")
            continue

    if updated:
        post_history.save_history(history)
    return updated


def _clamp(value, low, high):
    return max(low, min(high, value))


def compute_preferences():
    """Aggregates all checked posts into state/content_preferences.json.
    Every group is gated on MIN_SAMPLES -- groups below that just don't get
    an entry, and generate_post_text.py's own fallback (deterministic
    rotation, default interval) covers anything missing here."""
    history = post_history.load_history()
    # Emergency-alert posts are deliberately excluded here -- they're not
    # comparable content to a routine daily post (people don't "engage" with
    # a flood warning the way they do a seasonal photo or a normal check-in,
    # in either direction), so mixing their engagement numbers into
    # hook-weighting or the grounded-vs-plain comparison would skew both
    # away from what this loop is actually trying to learn. post_type
    # defaults to "daily" via .get() for every record written before this
    # field existed, so old history is unaffected by this filter.
    checked = [
        p for p in history["posts"]
        if p.get("engagement_checked") and p.get("engagement") and p.get("post_type", "daily") != "emergency_alert"
    ]

    sample_counts_hooks = {}
    totals_by_hook = {}
    grounded_totals = []
    plain_totals = []
    for p in checked:
        try:
            total = p["engagement"]["total"]
        except (KeyError, TypeError) as exc:
            # One malformed "checked" record (an engagement dict without
            # "total") must not halt preference-learning for every other
            # post, every run -- same reasoning as
            # update_pending_engagement's per-post isolation above.
            print(f"[compute_preferences] skipping malformed checked-post record "
                  f"({p.get('post_id', '<no post_id>')}): {exc}")
            continue

        if p.get("had_image"):
            grounded_totals.append(total)
        else:
            plain_totals.append(total)

        try:
            key = (p["slot"], p["hook_line"])
        except KeyError as exc:
            print(f"[compute_preferences] checked-post record "
                  f"({p.get('post_id', '<no post_id>')}) missing slot/hook_line -- "
                  f"counted toward grounded/plain totals above but skipped for "
                  f"hook weighting: {exc}")
            continue
        sample_counts_hooks[key] = sample_counts_hooks.get(key, 0) + 1
        totals_by_hook.setdefault(key, []).append(total)

    hook_weights = {"morning": {}, "afternoon": {}}
    sample_counts_flat = {}
    for (slot, hook), totals in totals_by_hook.items():
        sample_counts_flat[hook] = sample_counts_hooks[(slot, hook)]
        if sample_counts_hooks[(slot, hook)] < MIN_SAMPLES:
            continue
        slot_avg = sum(sum(v) / len(v) for (s, h), v in totals_by_hook.items() if s == slot) / max(
            len([1 for (s, h) in totals_by_hook if s == slot]), 1)
        this_avg = sum(totals) / len(totals)
        weight = _clamp(this_avg / slot_avg, WEIGHT_FLOOR, WEIGHT_CEILING) if slot_avg else 1.0
        hook_weights.setdefault(slot, {})[hook] = round(weight, 2)

    # grounded (had_image) vs plain totals were already collected above in
    # the same safe pass -- nudge the interval gradually, bounded

    prefs = _load_existing_preferences()
    interval = prefs.get("grounded_post_interval_days", 4)
    try:
        interval = int(interval)
    except (TypeError, ValueError):
        interval = 4
    if len(grounded_totals) >= MIN_SAMPLES and len(plain_totals) >= MIN_SAMPLES:
        grounded_avg = sum(grounded_totals) / len(grounded_totals)
        plain_avg = sum(plain_totals) / len(plain_totals)
        if plain_avg > 0 and grounded_avg > plain_avg * 1.1:
            interval = interval - 1  # grounded posts clearly doing better -> a bit more often
        elif plain_avg > 0 and grounded_avg < plain_avg * 0.9:
            interval = interval + 1  # clearly doing worse -> a bit less often
    # Re-clamp unconditionally right before writing -- these bounds must
    # stay in sync with GROUNDED_POST_INTERVAL_MIN/MAX in
    # generate_post_text.py. A hand-edited or otherwise out-of-bounds
    # existing value should never get carried forward/written back
    # unclamped, regardless of which branch above ran (or whether any did).
    interval = _clamp(interval, 3, 6)

    new_prefs = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "hook_weights": hook_weights,
        "grounded_post_interval_days": interval,
        "sample_counts": {
            "hooks": sample_counts_flat,
            "grounded_vs_plain": {"grounded": len(grounded_totals), "plain": len(plain_totals)},
        },
    }
    os.makedirs(os.path.dirname(PREFERENCES_PATH), exist_ok=True)
    with open(PREFERENCES_PATH, "w") as f:
        import json
        json.dump(new_prefs, f, indent=2)
        f.write("\n")
    return new_prefs


def _load_existing_preferences():
    try:
        import json
        with open(PREFERENCES_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    access_token = os.environ.get("FB_PAGE_ACCESS_TOKEN")
    if not access_token:
        print("FB_PAGE_ACCESS_TOKEN not set -- cannot check engagement. Exiting.")
        return 1

    print(f"Checking posts older than {MIN_HOURS_BEFORE_CHECK}h with unchecked engagement...")
    updated = update_pending_engagement(access_token)
    print(f"Updated {updated} post(s).")

    print("Recomputing content preferences from all checked posts...")
    prefs = compute_preferences()
    print(f"grounded_post_interval_days = {prefs['grounded_post_interval_days']}")
    print(f"hook sample counts = {prefs['sample_counts']['hooks']}")
    print(f"grounded vs plain samples = {prefs['sample_counts']['grounded_vs_plain']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
