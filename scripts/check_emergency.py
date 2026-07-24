"""
Emergency alert orchestrator: checks for active flood/fire/evacuation/
disaster conditions from four sources -- (1) NWS's public active-alerts
feed, (2) config/emergency_override.json, a manual backstop David edits by
hand in this repo, (3) restriction.override on David's own
govallecito-conditions Worker, a SECOND independent manual backstop (see
_check_worker_override() below for the field contract), and (4) an
escalation in fetch_conditions.fetch_fire_status()'s stage/nearby-wildfire
numbers (sourced from that same Worker as of 2026-07-24; a stage increase,
or a newly-higher nearby-wildfire count) -- and immediately posts a
safety-priority-variant card for anything genuinely NEW, with no scheduling
wait and no manual-approval gate. That's the whole point of this file:
David's instruction was "posted immediately without review."

Why TWO manual backstops (2 and 3) instead of one: neither La Plata
County's current resident notification system (LPC Alerts, formerly branded
CodeRED) nor its predecessor has ever exposed a public API or feed a script
could poll (confirmed 2026-07-24) -- so a real county evacuation order only
reaches this bot if David tells it by hand, through one of these two
channels. They're not redundant: config/emergency_override.json is editable
straight from GitHub's own web UI from a phone with zero code context (and
pushing it triggers this workflow within seconds -- see below);
restriction.override lives in code David already maintains for other
reasons and may already be open when something happens, but a change there
only gets picked up on the next scheduled poll (also see below).

Runs via .github/workflows/emergency-alert.yml on both a frequent schedule
AND an instant push trigger for config/emergency_override.json.
"Immediately" here honestly means "within ~10-15 minutes at worst for the
automated NWS feed and for a Worker-side restriction.override change, or
within seconds of a git push for a config/emergency_override.json edit" --
not truly real-time, and the Worker path specifically does NOT get the
instant-push speed, since it lives outside this repo and GitHub has no way
to know the moment David deploys a change to it. See the README for the
full honest version of that promise, including the coverage gap disclosed
in fetch_conditions.fetch_active_alerts()'s docstring.

Respects the existing DRY_RUN toggle exactly like main.py does. This is NOT
the "review gate" David asked to remove -- that instruction was about not
requiring a person to approve each alert before it posts. DRY_RUN is a
different thing: David's own opt-in safety net for testing this file's
logic without anything going out live. It stays in place, governed by the
same repo variable as the two scheduled daily posts, until he flips it to
"false".

De-duplication is state-based (state/emergency_alert_state.json) so the
same still-active NWS alert, still-open manual override (either kind), or
still-elevated fire stage doesn't get re-posted every single run -- only a
genuinely NEW alert id, a CHANGED override, or an INCREASE in fire
stage/nearby-wildfire count triggers a new post. A stage or count DECREASE (restrictions being
lifted) is deliberately not treated as alert-worthy here -- that's good
news, not an emergency, and it already shows up naturally in the next
scheduled daily post same as it always has.
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_conditions
import generate_post_text
import render_card
import post_to_facebook
import post_history

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OVERRIDE_PATH = os.path.join(REPO_ROOT, "config", "emergency_override.json")
STATE_PATH = os.path.join(REPO_ROOT, "state", "emergency_alert_state.json")

DEFAULT_STATE = {
    "posted_alert_ids": [],
    "manual_override": {"last_posted_fingerprint": None},
    "worker_override": {"last_posted_fingerprint": None},
    "fire_escalation": {"last_posted_stage": None, "last_posted_nearby_count": None},
}


def _load_state():
    if not os.path.exists(STATE_PATH):
        return json.loads(json.dumps(DEFAULT_STATE))  # cheap deep copy
    try:
        with open(STATE_PATH) as f:
            loaded = json.load(f)
        # Merge onto the default shape rather than trusting the file's shape
        # outright -- an older/partial state file (or one hand-edited to
        # clear something) shouldn't be able to crash a later dict access
        # here just because a key is missing.
        merged = json.loads(json.dumps(DEFAULT_STATE))
        if isinstance(loaded.get("posted_alert_ids"), list):
            merged["posted_alert_ids"] = loaded["posted_alert_ids"]
        if isinstance(loaded.get("manual_override"), dict):
            merged["manual_override"].update(loaded["manual_override"])
        if isinstance(loaded.get("worker_override"), dict):
            merged["worker_override"].update(loaded["worker_override"])
        if isinstance(loaded.get("fire_escalation"), dict):
            merged["fire_escalation"].update(loaded["fire_escalation"])
        return merged
    except Exception as exc:
        # Same posture as post_history.load_history(): a corrupt (not
        # missing) state file is not the same as "no state yet." Back it up
        # rather than silently discarding it, even though the worst case of
        # losing this particular file is mild (a handful of already-seen
        # alerts might get re-posted once) -- consistent with this
        # project's established handling of every other state file.
        backup_path = STATE_PATH + ".corrupt-backup"
        try:
            os.replace(STATE_PATH, backup_path)
            print(f"[check_emergency] {STATE_PATH} failed to parse ({exc}); backed up to "
                  f"{backup_path} and starting fresh. Worst case: a couple of already-seen "
                  "alerts get re-posted once.")
        except OSError as backup_exc:
            print(f"[check_emergency] {STATE_PATH} failed to parse ({exc}), and the backup "
                  f"attempt also failed ({backup_exc}). Starting fresh anyway.")
        return json.loads(json.dumps(DEFAULT_STATE))


def _save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    # Same atomic-write pattern as post_history.save_history() -- temp file
    # + rename, so a run that gets killed mid-write can't leave a half
    # written, corrupt state file behind.
    tmp_path = STATE_PATH + f".tmp-{os.getpid()}"
    with open(tmp_path, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")
    os.replace(tmp_path, STATE_PATH)


def _load_override():
    try:
        with open(OVERRIDE_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        print(f"[check_emergency] {OVERRIDE_PATH} exists but failed to parse ({exc}); "
              "treating as 'no active override' this run rather than crashing.")
        return {}


def _fingerprint(*parts):
    return hashlib.sha256("||".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _check_manual_override(state):
    """Read-only: returns an alert dict if the override is active AND its
    content differs from what was last successfully posted, else None. Does
    NOT mutate state -- the caller only updates state after a successful
    post (see main())."""
    override = _load_override()
    if not override.get("active"):
        return None
    category = override.get("category") or "disaster"
    if category not in generate_post_text.ALERT_CATEGORY_DISPLAY:
        print(f"[check_emergency] emergency_override.json has an unrecognized category "
              f"{category!r} -- treating as 'disaster'. Valid categories: "
              f"{sorted(generate_post_text.ALERT_CATEGORY_DISPLAY)}")
        category = "disaster"
    fp = _fingerprint(category, override.get("headline"), override.get("details"), override.get("source"))
    if state["manual_override"]["last_posted_fingerprint"] == fp:
        return None  # this exact override content was already posted
    return {
        "id": f"manual-override-{fp}",
        "kind": "manual_override",
        "fingerprint": fp,
        "event": "Manually flagged emergency",
        "category": category,
        "headline": override.get("headline") or "Emergency alert",
        "description": override.get("details", ""),
        "source_name": override.get("source") or "GoVallecito",
        "source_url": override.get("source_url", ""),
    }


def _check_worker_override(state, fire):
    """Read-only: returns an alert dict if David's own Worker reports an
    active override -- restriction.override truthy on the raw snapshot
    fetch_conditions.py passes through as fire["_restriction_raw"] -- AND its
    content differs from what was last successfully posted, else None. Does
    NOT mutate state -- same convention as _check_manual_override() above.

    This is a SECOND, independent way to flag a manual emergency; it
    coexists with config/emergency_override.json rather than replacing it
    (see the module docstring for why there are two). David asked
    (2026-07-24) about connecting straight to the county's own evacuation
    system -- not possible, neither CodeRED nor its LPC Alerts replacement
    expose a public feed (see fetch_conditions.fetch_active_alerts()'s
    docstring) -- so this is the closest practical substitute: flip one
    field in code David already controls
    (govallecito-conditions.dkontje.workers.dev) and it reaches Facebook on
    the next poll (~10-15 min worst case; NOT instant -- see the module
    docstring), no separate change in this repo required.

    Field contract, all on the raw `restriction` object the Worker returns
    (conditions.json's "restriction" key) -- this is a proposed convention,
    not something the Worker sends today, so every field below is read
    defensively and falls back to generic text if absent:
      override           -- bool. Everything else here is optional --
                             flipping just this one flag is enough to
                             produce a real, if generically worded, post.
      overrideCategory    -- one of generate_post_text.ALERT_CATEGORY_DISPLAY's
                             keys ("flood"/"fire"/"evacuation"/"disaster").
                             Unrecognized or missing -> "disaster".
      overrideHeadline    -- short headline string.
      overrideDetails     -- longer description string.
      overrideSource      -- attribution shown in the post (e.g. "La Plata
                             County OEM"). Missing -> "GoVallecito".
      overrideSourceUrl   -- link included in the post if present.
    """
    restriction = (fire or {}).get("_restriction_raw") or {}
    if not restriction.get("override"):
        return None
    category = restriction.get("overrideCategory") or "disaster"
    if category not in generate_post_text.ALERT_CATEGORY_DISPLAY:
        print(f"[check_emergency] restriction.overrideCategory has an unrecognized value "
              f"{category!r} -- treating as 'disaster'. Valid categories: "
              f"{sorted(generate_post_text.ALERT_CATEGORY_DISPLAY)}")
        category = "disaster"
    fp = _fingerprint(category, restriction.get("overrideHeadline"), restriction.get("overrideDetails"), restriction.get("overrideSource"))
    if state["worker_override"]["last_posted_fingerprint"] == fp:
        return None  # this exact override content was already posted
    return {
        "id": f"worker-override-{fp}",
        "kind": "worker_override",
        "fingerprint": fp,
        "event": "Worker-flagged emergency",
        "category": category,
        "headline": restriction.get("overrideHeadline") or "Emergency alert",
        "description": restriction.get("overrideDetails", ""),
        "source_name": restriction.get("overrideSource") or "GoVallecito",
        "source_url": restriction.get("overrideSourceUrl", ""),
    }


def _find_new_nws_alerts(state, active_alerts):
    """Read-only from the caller's perspective except for one harmless,
    idempotent side effect: pruning ids that are no longer active out of
    state["posted_alert_ids"] (garbage collection, not a "mark as posted"
    action -- safe to redo every run, and means an alert that expires and
    genuinely recurs later isn't permanently suppressed by a stale id)."""
    active_ids = {a["id"] for a in active_alerts if a.get("id")}
    state["posted_alert_ids"] = [i for i in state["posted_alert_ids"] if i in active_ids]
    already = set(state["posted_alert_ids"])
    return [
        {**a, "kind": "nws_alert"}
        for a in active_alerts
        if a.get("id") and a["id"] not in already
    ]


def _check_fire_escalation(state, fire):
    """Read-only: returns an alert dict only on a genuine INCREASE (stage up,
    or nearby-wildfire count up) versus the last value we alerted on. A
    decrease, or no fire data at all, returns None. Assumes the baseline has
    already been recorded by main() on this repo's first-ever run (see
    there) -- so a None here on every subsequent run just means "nothing
    changed," not "never checked before."""
    if not fire:
        return None
    try:
        stage = int(fire.get("stage", 0))
    except (TypeError, ValueError):
        stage = 0
    try:
        nearby_count = int((fire.get("nearby_wildfires") or {}).get("count", 0))
    except (TypeError, ValueError):
        nearby_count = 0

    fe = state["fire_escalation"]
    last_stage = fe["last_posted_stage"] or 0
    last_count = fe["last_posted_nearby_count"] or 0
    if stage <= last_stage and nearby_count <= last_count:
        return None

    stage_label = fire.get("stage_label") or f"Stage {stage} fire restrictions"
    raw_summary = fire.get("restrictions_summary", "")
    nearby_note = (fire.get("nearby_wildfires") or {}).get("note", "")
    description = " ".join(p for p in [raw_summary, nearby_note] if p)
    return {
        "id": f"fire-escalation-{stage}-{nearby_count}",
        "kind": "fire_escalation",
        "stage": stage,
        "nearby_count": nearby_count,
        "event": "Fire status escalation",
        "category": "fire",
        "headline": stage_label,
        "description": description,
        "source_name": fire.get("source") or "San Juan National Forest / La Plata County",
        "source_url": fire.get("source_url", ""),
    }


def main():
    print(f"=== GoVallecito emergency check: {datetime.now(timezone.utc).isoformat()} ===")
    state = _load_state()

    conditions = fetch_conditions.fetch_all()
    fire = conditions.get("fire")
    active_alerts = fetch_conditions.fetch_active_alerts()
    print(f"NWS active alerts matching our categories: {len(active_alerts)}")
    print(f"Worker restriction.override flag: "
          f"{bool((fire or {}).get('_restriction_raw', {}).get('override'))}")

    fe = state["fire_escalation"]
    if fire and fe["last_posted_stage"] is None and fe["last_posted_nearby_count"] is None:
        # First time this repo has ever run this check -- record today's
        # fire_status.json values as the starting baseline rather than
        # treating an already-true condition as a brand new escalation the
        # moment this feature goes live. Only genuine increases FROM HERE
        # count. Saved immediately so a crash later in this same run can't
        # lose this baseline and cause a false escalation alert next run.
        try:
            baseline_stage = int(fire.get("stage", 0))
        except (TypeError, ValueError):
            baseline_stage = 0
        try:
            baseline_count = int((fire.get("nearby_wildfires") or {}).get("count", 0))
        except (TypeError, ValueError):
            baseline_count = 0
        fe["last_posted_stage"] = baseline_stage
        fe["last_posted_nearby_count"] = baseline_count
        print(f"[check_emergency] First-ever run: recording fire status baseline "
              f"(stage={baseline_stage}, nearby_count={baseline_count}) without alerting on it.")
        _save_state(state)

    new_events = []
    manual = _check_manual_override(state)
    if manual:
        new_events.append(manual)
    worker_override = _check_worker_override(state, fire)
    if worker_override:
        new_events.append(worker_override)
    new_events.extend(_find_new_nws_alerts(state, active_alerts))
    fire_alert = _check_fire_escalation(state, fire)
    if fire_alert:
        new_events.append(fire_alert)

    if not new_events:
        print("Nothing new to alert on. Exiting.")
        _save_state(state)  # persists _find_new_nws_alerts' pruning even when nothing posts
        return 0

    print(f"{len(new_events)} new alert-worthy event(s) -- posting immediately, "
          "no scheduling wait, no manual-approval gate.")
    os.makedirs("output", exist_ok=True)

    for i, alert in enumerate(new_events):
        print(f"--- Alert {i + 1}/{len(new_events)}: [{alert['category']}] {alert['headline']} ---")
        try:
            post = generate_post_text.build_alert_post(conditions, alert, dt=datetime.now())
            print(f"  meta: {post['meta']}")

            image_path = os.path.join("output", f"alert_card_{i}.png")
            render_card.render_card(post["card_data"], image_path)
            print(f"  Rendered card -> {image_path}")

            result = post_to_facebook.post_photo(image_path, post["caption"])
            print(f"  Posted. Result: {result}")

            post_id = result.get("post_id") or result.get("id")
            if result.get("dry_run"):
                pass  # nothing to log -- no real post_id, matches main.py's own convention
            elif post_id:
                post_history.record_post(post_id, datetime.now().astimezone().isoformat(), "emergency", post["meta"])
                print(f"  Logged to state/post_history.json (post_id={post_id})")
            else:
                print("  WARNING: a live alert post appears to have succeeded but the response "
                      f"had no post_id/id to log (result={result}). This post will NOT be "
                      "tracked in post_history.json -- investigate the Graph API response shape.")

            # Only mark this specific alert "handled" (so it isn't re-posted
            # next run) AFTER a successful post attempt above -- dry-run
            # counts as successful here too, since exercising this exact
            # decision path safely is the whole point of DRY_RUN. If
            # post_photo() raised, we never reach this block, so a genuine
            # posting failure is retried next run instead of silently marked
            # done -- and it does NOT stop the loop from trying any other
            # pending alert in this same run.
            if alert.get("kind") == "manual_override":
                state["manual_override"]["last_posted_fingerprint"] = alert["fingerprint"]
            elif alert.get("kind") == "worker_override":
                state["worker_override"]["last_posted_fingerprint"] = alert["fingerprint"]
            elif alert.get("kind") == "fire_escalation":
                state["fire_escalation"]["last_posted_stage"] = alert["stage"]
                state["fire_escalation"]["last_posted_nearby_count"] = alert["nearby_count"]
            else:  # nws_alert
                state["posted_alert_ids"] = list(set(state["posted_alert_ids"]) | {alert["id"]})
            _save_state(state)
        except Exception as exc:
            print(f"  FAILED to post this alert ({exc}) -- NOT marking it handled, so it will "
                  "be retried next run. Continuing to any other pending alert in this run.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
