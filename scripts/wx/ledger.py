"""
A per-day record of which slots actually produced a post.

WHY THIS EXISTS, and it is the most expensive lesson this project has learned.

The original design ran an hourly cron and asked `SLOT_HOURS.get(now.hour)`,
so a run only posted if it happened to execute during the 5 o'clock hour in
Mountain Time. That is correct only if the hourly cron is actually hourly.

It is not. Over 2026-08-31 to 2026-09-07 the workflow executed 4 to 7 times a
day, not 24, at effectively arbitrary minutes: 00:19, 04:55, 08:00, 10:56,
13:31, 15:42, 17:21. GitHub Actions drops and defers scheduled runs under
platform load, and a workflow sharing a `concurrency` group can have its
pending run evicted by the next one queued. On 2026-09-03 a run landed at
04:55 and the next at 08:43, so the 5 o'clock hour was never sampled and no
post went out. Four of eight days never sampled the posting hour at all.

The fix is to stop requiring an exact hour to be hit. A slot now owns a WINDOW
of local hours, and any surviving run inside that window posts, unless this
ledger says the slot already went out today. The ledger is what makes a wide
window safe: without it, four runs inside a four hour window would post four
times.

The entry is written only after a draft actually exists (published, held, or
blocked). A run that aborts on missing data does NOT consume the day, so the
next surviving run inside the window retries it. That is deliberate: on
2026-09-04 the 05:46 run reached the posting hour and then died because two
Open-Meteo bands failed, and under the old design that day was simply lost.
"""

import json
import os
from datetime import datetime

from . import constants as C


def state_dir():
    """Resolve the state directory the same way run_forecast does.

    Relative to the working directory, never to __file__: an earlier version
    resolved from the module path and the test suite wrote fixture drafts over
    a real one.
    """
    return os.environ.get("WX_STATE_DIR") or "state"


def path():
    return os.path.join(state_dir(), "post_ledger.json")


def load():
    try:
        with open(path()) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data):
    try:
        os.makedirs(state_dir(), exist_ok=True)
        with open(path(), "w") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
    except OSError as exc:
        # A ledger write failure must never take down a post that already
        # succeeded. The cost is a possible duplicate, which is visible and
        # fixable; a crash here would lose the post itself.
        print(f"[ledger] could not write {path()}: {exc}")


def done(date_iso, slot):
    """Has `slot` already produced a draft for `date_iso`?"""
    return bool((load().get(date_iso) or {}).get(slot))


def record(date_iso, slot, note=None):
    data = load()
    day = data.setdefault(date_iso, {})
    day[slot] = {
        "at": C.local_now().isoformat(timespec="seconds"),
        "note": note or "",
    }
    _prune(data)
    _save(data)


def flag(date_iso, name):
    """Mark a one-per-day non-post event, e.g. that a miss was reported."""
    data = load()
    data.setdefault(date_iso, {})[name] = {
        "at": C.local_now().isoformat(timespec="seconds")}
    _prune(data)
    _save(data)


def flagged(date_iso, name):
    return bool((load().get(date_iso) or {}).get(name))


def _prune(data, keep=60):
    """Keep the file small enough to read by eye in a diff."""
    for key in sorted(data)[:-keep]:
        data.pop(key, None)


def recent_days(n=14):
    """The last n dated entries, newest first. For the miss report."""
    data = load()
    return [(d, data[d]) for d in sorted(data, reverse=True)[:n]]


def missing_since(first_iso, slot, today_iso):
    """Dates between first_iso and today_iso (exclusive) with no `slot` entry.

    Used by the miss alarm so a report can say "this is the third day in a
    row," which is a different message from "one run got unlucky."

    Only counts days the ledger has SOME entry for. A day with no entry at all
    is a day this file cannot speak to: it predates the ledger, or the repo was
    quiet. Counting those made the very first miss report announce eight
    consecutive failures on an empty file, which is the kind of alarm people
    learn to ignore.
    """
    try:
        start = datetime.fromisoformat(first_iso).date()
        end = datetime.fromisoformat(today_iso).date()
    except ValueError:
        return []
    data = load()
    out = []
    cur = start
    while cur < end:
        iso = cur.isoformat()
        day = data.get(iso)
        if day and not day.get(slot):
            out.append(iso)
        cur = cur.fromordinal(cur.toordinal() + 1)
    return out
