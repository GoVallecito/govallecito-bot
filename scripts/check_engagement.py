"""
Looks back at posts that are at least 48 hours old, pulls their reaction /
comment / share counts from the Graph API, and (gradually, gated on sample
size) turns that into state/content_preferences.json -- the weights
generate_post_text.py reads for hook-line selection and how often "grounded"
seasonal posts happen.

Run via .github/workflows/engagement-check.yml (daily). Can also be run by
hand: python scripts/check_engagement.py

WHAT WAS LEARNED THE HARD WAY (2026-10-10). From the first run on
2026-07-26 until this rewrite, every single engagement fetch failed with
Graph error #10 and nothing noticed: the workflow stayed green, failures were
retried for 14 days and then the post was silently written off as
"engagement_unavailable". 69 posts went that way and content_preferences.json
never received one data point. A read-only probe (run 38084760366) settled
why, against the live API:

  * The Page token HAS pages_read_engagement and can read each post's id,
    created_time and shares.
  * reactions and comments on a Page post are user content. They need
    pages_read_user_content, which the token was never minted with. Meta's
    error for the old `likes` field misleadingly names pages_read_engagement;
    the reactions and comments errors name pages_read_user_content correctly.
  * Sending the token as a Bearer header vs. an access_token parameter makes
    no difference.
  * /{post-id}/insights?metric=post_impressions is rejected outright in v25
    (#100, "must be a valid insights metric"), on top of Meta returning no
    insights for Pages under ~100 followers. The impressions code was removed
    rather than repaired: there is no reach data to collect at this size.

So the rules this file now follows:

1. FIELDS. reactions (every reaction type, not just likes), comments and
   shares -- each read with limit(0) so only the counts come back. No name
   of anyone who reacted or commented is ever fetched, let alone written to
   state/ in this public repo.
2. CLASSIFY EVERY FAILURE. A failed read is one of:
     permission  the token can see the post but not its engagement (or the
                 token itself is invalid). NOT the post's fault, so it never
                 counts toward giving up on a post; the run stops calling
                 Facebook and exits 2 so the workflow goes red.
     gone        the post itself can no longer be read (deleted, or never
                 existed). Told apart from `permission` by a second, minimal
                 read of the post's id: the token can read ids of posts that
                 exist (the probe proved that), so an id read that fails too
                 means the post is the problem. Recorded once, never retried.
     transient   network, 5xx, rate limiting, anything else. Retried next
                 run; written off only after 14 days AND 3 attempts.
3. NEVER FAIL SILENTLY. If posts were due and not one could be read, exit 2
   (red run) even if every failure looked transient.
4. RECOVERY. Posts written off before this rewrite carry
   engagement_unavailable without an engagement_unavailable_reason. They are
   re-opened and checked again -- lifetime counts are still on Facebook.
   Recording a reason on every new write-off is what keeps this a one-time
   migration rather than an endless retry loop.

On "learning": with a page this small (6 followers as of 2026-10-10), don't
expect this file to say anything meaningful for a long while. MIN_SAMPLES
(15) per hook line is far more data than the page produces; see the comments
in generate_post_text.py for why guessing from a few data points would be
worse than not guessing.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import post_history

GRAPH_API_VERSION = "v25.0"
MIN_HOURS_BEFORE_CHECK = 48
MIN_SAMPLES = 15
PREFERENCES_PATH = os.path.join(post_history.REPO_ROOT, "state", "content_preferences.json")

WEIGHT_FLOOR = 0.6
WEIGHT_CEILING = 1.6

ENGAGEMENT_FIELDS = ",".join((
    "reactions.summary(total_count).limit(0)",
    "comments.summary(true).limit(0)",
    "shares",
))

# Give up on a post only when BOTH are true. Hours alone used to be the rule,
# which meant a post re-opened long after it was published would be written
# off again on its first transient hiccup.
MAX_HOURS_BEFORE_GIVING_UP = 24 * 14
MIN_ATTEMPTS_BEFORE_GIVING_UP = 3

# Exit code for "the run worked, but the feedback loop is broken" -- the
# workflow commits whatever was learned and THEN goes red (see
# engagement-check.yml). Distinct from 1 (crash / misconfiguration).
EXIT_LOOP_BROKEN = 2

OK, PERMISSION, GONE, TRANSIENT = "ok", "permission", "gone", "transient"

# Graph error codes meaning "this token can't do that", as opposed to
# "something went wrong this time". 10 / 200-299 are permission errors,
# 190 is an invalid or expired token, 102 is a session error.
_PERMISSION_CODES = {10, 102, 190}


def _hours_since(iso_timestamp):
    posted = datetime.fromisoformat(iso_timestamp)
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - posted).total_seconds() / 3600


def _graph_get(path, params, access_token, get=None):
    """(http_status, body_dict) or (None, None) on a network failure.
    The token rides in the Authorization header so it can never appear in a
    URL that a requests exception might print. Exceptions are reported by
    type only, for the same reason."""
    get = get or requests.get
    try:
        resp = get(f"https://graph.facebook.com/{GRAPH_API_VERSION}/{path}",
                   params=params, headers={"Authorization": f"Bearer {access_token}"},
                   timeout=20)
    except Exception as exc:  # noqa: BLE001
        print(f"  [graph] {path}: network failure ({type(exc).__name__})")
        return None, None
    try:
        body = resp.json()
    except ValueError:
        body = {}
    return resp.status_code, body if isinstance(body, dict) else {}


def _error_of(status, body):
    """The Graph error dict, {} for a network failure, or None on success."""
    if status is None:
        return {}
    err = body.get("error")
    if status >= 400 or err:
        return err if isinstance(err, dict) else {"message": f"HTTP {status}"}
    return None


def _is_permission_error(err):
    code = err.get("code")
    return isinstance(code, int) and (code in _PERMISSION_CODES or 200 <= code <= 299)


def _summary(err):
    return (f"code={err.get('code')} sub={err.get('error_subcode')} "
            f"{str(err.get('message', 'no message'))[:160]}")


def fetch_engagement(post_id, access_token, get=None):
    """Returns (kind, payload).

    (OK, {"reactions", "comments", "shares", "total"}) on success.
    Otherwise (PERMISSION | GONE | TRANSIENT, short error description).
    """
    status, body = _graph_get(post_id, {"fields": ENGAGEMENT_FIELDS}, access_token, get)
    err = _error_of(status, body)
    if err is None:
        def total_count(key):
            return ((body.get(key) or {}).get("summary") or {}).get("total_count") or 0
        reactions = total_count("reactions")
        comments = total_count("comments")
        # "shares" is absent entirely (not 0) on a post nobody has shared.
        shares = (body.get("shares") or {}).get("count") or 0
        return OK, {
            "reactions": reactions,
            "comments": comments,
            "shares": shares,
            "total": reactions + comments + shares,
        }
    if status is None:
        return TRANSIENT, "network failure"
    if not _is_permission_error(err) and not (err.get("code") == 100):
        return TRANSIENT, _summary(err)

    # A permission-shaped error. Is it the token, or is the post gone? Meta
    # answers a deleted post with #10 too ("Object does not exist, cannot be
    # loaded due to missing permission..."), so ask for the post's bare id:
    # the token can read that for any post that still exists.
    id_status, id_body = _graph_get(post_id, {"fields": "id"}, access_token, get)
    id_err = _error_of(id_status, id_body)
    if id_err is None:
        if err.get("code") == 100:
            return TRANSIENT, _summary(err)  # post exists; a bad field, not a missing permission
        return PERMISSION, _summary(err)
    if id_status is None:
        return TRANSIENT, "network failure on the id check"
    if err.get("code") == 190 or id_err.get("code") == 190:
        return PERMISSION, _summary(id_err)  # the token itself is dead
    return GONE, _summary(id_err)


def _needs_check(post):
    """A post is due if it was never checked, or if it was written off before
    failures carried a reason (the pre-2026-10-10 permission bug). Explicit
    `is True` rather than truthiness: a hand-edited history could hold the
    STRING "false", which is truthy."""
    if post.get("engagement_checked") is not True:
        return True
    return (post.get("engagement_unavailable") is True
            and post.get("engagement") is None
            and not post.get("engagement_unavailable_reason"))


def _mark(post, **fields):
    post.update(fields)
    post["engagement_checked"] = True
    post["engagement_checked_at"] = datetime.now(timezone.utc).isoformat()


def update_pending_engagement(access_token, get=None):
    """Checks every due post that's old enough and records what it finds.

    Returns a dict: updated, ok, gone, transient, permission (counts), plus
    attempted and loop_broken. loop_broken is True when the token cannot read
    engagement, or when posts were due and none could be read at all.
    """
    history = post_history.load_history()
    stats = {"updated": 0, "ok": 0, "gone": 0, "transient": 0, "permission": 0, "attempted": 0}
    permission_error = None
    for post in history["posts"]:
        try:
            if not _needs_check(post):
                continue
            hours_old = _hours_since(post["posted_at"])
            if hours_old < MIN_HOURS_BEFORE_CHECK:
                continue
            post_id = post["post_id"]
            stats["attempted"] += 1
            kind, payload = fetch_engagement(post_id, access_token, get)

            if kind == OK:
                _mark(post, engagement=payload, engagement_unavailable=False)
                post.pop("engagement_unavailable_reason", None)
                post.pop("engagement_attempts", None)
                stats["ok"] += 1
                stats["updated"] += 1
                print(f"  {post_id} ({post['posted_at'][:10]}): {payload}")
            elif kind == GONE:
                _mark(post, engagement=None, engagement_unavailable=True,
                      engagement_unavailable_reason="post_unreadable")
                stats["gone"] += 1
                stats["updated"] += 1
                print(f"  {post_id}: the post itself can't be read (deleted?) -- recorded, "
                      f"won't retry. {payload}")
            elif kind == PERMISSION:
                # Not this post's fault and the same for every post: stop
                # hammering the API and change nothing about this post.
                stats["permission"] += 1
                permission_error = payload
                print(f"  {post_id}: PERMISSION -- {payload}")
                break
            else:  # TRANSIENT
                stats["transient"] += 1
                attempts = int(post.get("engagement_attempts") or 0) + 1
                post["engagement_attempts"] = attempts
                stats["updated"] += 1  # the attempt counter changed
                if hours_old >= MAX_HOURS_BEFORE_GIVING_UP and attempts >= MIN_ATTEMPTS_BEFORE_GIVING_UP:
                    _mark(post, engagement=None, engagement_unavailable=True,
                          engagement_unavailable_reason="gave_up_transient")
                    print(f"  {post_id}: still failing after {attempts} attempts and "
                          f"{hours_old:.0f}h -- giving up. {payload}")
                else:
                    print(f"  {post_id}: failed this run (attempt {attempts}), will retry. {payload}")
        except Exception as exc:
            # One malformed record must not take down every other post's check.
            print(f"  [update_pending_engagement] skipping malformed post record "
                  f"({post.get('post_id', '<no post_id>')}): {type(exc).__name__}: {exc}")
            continue

    if stats["updated"]:
        post_history.save_history(history)

    # Broken = the token can't read engagement, or at least two posts were
    # due and not one could be read for a reason other than being deleted.
    # (One lone failure is allowed to be a blip; it is retried tomorrow,
    # when the next day's posts are due too.)
    stats["loop_broken"] = bool(permission_error) or (
        stats["ok"] == 0 and stats["transient"] >= 2)
    stats["permission_error"] = permission_error
    return stats


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
    raw_totals = {"reactions": 0, "comments": 0, "shares": 0}
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

        for k in raw_totals:
            value = p["engagement"].get(k)
            if isinstance(value, int):
                raw_totals[k] += value

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

    # Plain-sight summary of what the loop has actually collected, so a
    # human reading this file can tell "no data" from "data, all zeros"
    # without opening post_history.json. Not read by generate_post_text.py.
    collected = {
        "checked_count": len(checked),
        "totals": raw_totals,
    }

    new_prefs = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "hook_weights": hook_weights,
        "grounded_post_interval_days": interval,
        "sample_counts": {
            "hooks": sample_counts_flat,
            "grounded_vs_plain": {"grounded": len(grounded_totals), "plain": len(plain_totals)},
        },
        "collected": collected,
    }
    os.makedirs(os.path.dirname(PREFERENCES_PATH), exist_ok=True)
    with open(PREFERENCES_PATH, "w") as f:
        json.dump(new_prefs, f, indent=2)
        f.write("\n")
    return new_prefs


def _load_existing_preferences():
    try:
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
    stats = update_pending_engagement(access_token)
    print(f"Attempted {stats['attempted']}: {stats['ok']} read, {stats['gone']} unreadable "
          f"(deleted?), {stats['transient']} failed this run, "
          f"{stats['permission']} stopped on a permission error.")

    print("Recomputing content preferences from all checked posts...")
    prefs = compute_preferences()
    print(f"grounded_post_interval_days = {prefs['grounded_post_interval_days']}")
    print(f"hook sample counts = {prefs['sample_counts']['hooks']}")
    print(f"grounded vs plain samples = {prefs['sample_counts']['grounded_vs_plain']}")
    print(f"collected so far = {prefs['collected']}")

    if stats["permission_error"]:
        print("::error title=Engagement loop broken: token permission::"
              "The Page token can read posts but not their reactions/comments "
              f"({stats['permission_error']}). Re-mint FB_PAGE_ACCESS_TOKEN with "
              "pages_read_user_content added -- see README step 2.")
        return EXIT_LOOP_BROKEN
    if stats["loop_broken"]:
        print(f"::error title=Engagement loop broken::{stats['attempted']} post(s) were due and "
              "not one could be read. Check the per-post lines above.")
        return EXIT_LOOP_BROKEN
    return 0


if __name__ == "__main__":
    sys.exit(main())
