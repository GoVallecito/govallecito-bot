"""
Reads/writes state/post_history.json -- the durable record of what got
posted and (later) how it did. This is the memory the engagement-learning
loop runs on.

GitHub Actions runners are thrown away after every run, so "durable" here
means the workflow commits this file back to the repo with git after each
run that changes it (see .github/workflows/*.yml). This module only handles
the JSON read/write; the git commit+push is a workflow step, not Python's
job -- keeps the concerns separate and makes the git side easy to see/audit
directly in the YAML.
"""

import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_PATH = os.path.join(REPO_ROOT, "state", "post_history.json")


def load_history():
    if not os.path.exists(HISTORY_PATH):
        return {"posts": []}
    try:
        with open(HISTORY_PATH) as f:
            return json.load(f)
    except Exception as exc:
        # A corrupt (as opposed to simply missing) history file is NOT the
        # same as "no history yet" -- treating it that way silently would
        # let the very next save overwrite what might be years of post and
        # engagement data. Back up the unreadable file so nothing is lost,
        # warn loudly, and only then fall back to an empty history so the
        # bot can still run.
        backup_path = HISTORY_PATH + ".corrupt-backup"
        try:
            os.replace(HISTORY_PATH, backup_path)
            print(f"[post_history] {HISTORY_PATH} exists but failed to parse ({exc}); "
                  f"backed up the unreadable file to {backup_path} and starting from empty "
                  "history. This should be investigated -- it likely means engagement/"
                  "learning history was lost.")
        except OSError as backup_exc:
            print(f"[post_history] {HISTORY_PATH} exists but failed to parse ({exc}), and "
                  f"the backup attempt also failed ({backup_exc}). Starting from empty "
                  "history anyway; the corrupt file has NOT been moved, so check it manually.")
        return {"posts": []}


def save_history(history):
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    # Write to a temp file and atomically rename into place, rather than
    # truncating HISTORY_PATH directly -- if two runs ever do overlap (see
    # the concurrency guard added to the workflow YAML, which is the primary
    # fix for that), this at least guarantees the file is always either the
    # old complete JSON or the new complete JSON, never a half-written/
    # corrupt in-between state.
    tmp_path = HISTORY_PATH + f".tmp-{os.getpid()}"
    with open(tmp_path, "w") as f:
        json.dump(history, f, indent=2)
        f.write("\n")
    os.replace(tmp_path, HISTORY_PATH)


def record_post(post_id, posted_at_iso, slot, meta):
    """Appends one entry. meta is generate_post_text.build_post()'s (or
    build_alert_post()'s) "meta" dict: hook_line, slot, had_image,
    image_topic, fire_stage -- plus, for an emergency alert post,
    post_type/alert_category/alert_id.

    post_type defaults to "daily" via .get() below, so every record written
    before this field existed is implicitly "daily" too -- reading code
    should always use .get("post_type", "daily") rather than assume the key
    is present, since old history entries genuinely won't have it.
    check_engagement.py's compute_preferences() relies on this default to
    exclude emergency-alert posts from the routine engagement-learning
    stats (an alert's engagement isn't comparable to a routine post's, and
    mixing them in would skew what that loop is trying to measure)."""
    history = load_history()
    history["posts"].append({
        "post_id": post_id,
        "posted_at": posted_at_iso,
        "slot": slot,
        "hook_line": meta.get("hook_line"),
        "had_image": meta.get("had_image", False),
        "image_topic": meta.get("image_topic"),
        "fire_stage": meta.get("fire_stage"),
        "post_type": meta.get("post_type", "daily"),
        "alert_category": meta.get("alert_category"),
        "alert_id": meta.get("alert_id"),
        "engagement_checked": False,
        "engagement": None,
    })
    save_history(history)
    return history
