"""
Turn a missed daily post into a signal.

THE FAILURE THIS EXISTS FOR: between 2026-08-26 and 2026-09-26 the conditions card
went out for 17 of 64 slots. Every workflow run was green, every run exited zero,
and nothing anywhere said a post was missing; it was found by counting entries in
post_history.json. The forecaster learned the same lesson on 2026-09-07 and grew an
alarm (scripts/wx/run_forecast.py: _report_miss_if_needed). This is the daily card's.

The rule worth keeping: alert on the ABSENCE of the expected thing, not only on
errors. Errors were never the problem.

WHEN IT FIRES. Once a slot's window has closed with no daily post recorded for it
on that Denver date, the next run that executes at all opens ONE GitHub Issue (the
notification channel the forecaster already uses: no new account, no new secret,
it emails the repo owner). It also looks back at yesterday, so a day with no run
after the window closed is still reported by the first run of the next day.
"Reported" is remembered in state/daily_post_state.json (already committed back by
the workflow) and by an open issue with the same title, so nothing is filed twice.

WHEN IT STAYS QUIET. A dry run (DRY_RUN=true) posts nothing by design; alarming
would be noise. Forced test runs never call this. Nothing fires before a window
has closed, so the 9am run does not report a 2pm post that has not happened.
"""
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import generate_post_text
from wx import notify

STATE_KEY = "miss_reports"     # { "2026-09-25": ["morning", "afternoon"] }
LOOKBACK_DAYS = 7
KEEP_DAYS = 14                 # how long "already reported" is remembered


def _dry_run():
    return (os.environ.get("DRY_RUN") or "").strip().lower() in ("1", "true", "yes")


def missed_slots(now, main, history):
    """[(date, slot)] for today and yesterday whose window has closed with no daily post.
    `main` is scripts/main.py (passed in to avoid a circular import): it owns the windows
    and the once-per-slot check."""
    out = []
    for back in (1, 0):
        day = now - timedelta(days=back)
        for slot, (_lo, hi) in main.SLOT_WINDOWS.items():
            closed = back == 1 or now.hour >= hi
            if closed and not main.slot_already_posted(slot, day, history):
                out.append((day.date().isoformat(), slot))
    return out


def week_of_misses(now, main, history):
    """Every closed slot without a post in the last LOOKBACK_DAYS days, as 'date slot'."""
    misses = []
    for back in range(LOOKBACK_DAYS, -1, -1):
        day = now - timedelta(days=back)
        for slot, (_lo, hi) in main.SLOT_WINDOWS.items():
            closed = back > 0 or now.hour >= hi
            if closed and not main.slot_already_posted(slot, day, history):
                misses.append(f"{day.date().isoformat()} {slot}")
    return misses


def _body(date_iso, slot, window, misses):
    lo, hi = window
    lines = [
        f"No **{slot}** conditions card went out for **{date_iso}**.",
        "",
        f"Its window ({lo}:00-{hi}:00 Denver) closed with no daily post in `state/post_history.json`.",
        "That means either no scheduled run executed inside the window, or every run that did",
        "aborted or failed before posting.",
        "",
        "**Where to look, in order:**",
        "",
        "1. The Actions tab, workflow *Daily Vallecito Conditions Post*: were there runs between",
        f"   {lo}:00 and {hi}:00 Denver that day? If not, GitHub dropped the schedule (it fires only",
        "   about 5-7 of the 24 hourly runs) and this is not a code fault.",
        "2. If runs did land in the window, open one: a failed Facebook call or a missing data source",
        "   is in its log. A run that dies before posting leaves the slot open for the next run.",
        "3. `DRY_RUN` in the repo variables must be `false`, or nothing posts at all.",
        "4. The token: an expired `FB_PAGE_ACCESS_TOKEN` fails every post with a Graph API error.",
        "",
    ]
    recent = [m for m in misses if m != f"{date_iso} {slot}"]
    if recent:
        lines += [f"**{len(misses)} missed slots in the last {LOOKBACK_DAYS} days:** " + ", ".join(misses), "",
                  "More than a couple a week is a pattern. If the runs are landing outside the windows,",
                  "the fix is a more reliable trigger (a Cloudflare Worker cron calling `workflow_dispatch`),",
                  "not more code here.", ""]
    return "\n".join(lines)


def _open_issue(title, body):
    repo, token = notify._repo(), notify._token()
    if not repo or not token:
        print("=" * 66 + f"\n{title}\n" + "=" * 66 + f"\n{body}")
        return {"notified": False, "reason": "no GITHUB_REPOSITORY/GITHUB_TOKEN"}
    if notify._open_issue_titled(repo, token, title):
        return {"notified": True, "duplicate": True}
    import json
    import urllib.error
    import urllib.request

    def _post(with_labels):
        fields = {"title": title, "body": body}
        if with_labels:
            fields["labels"] = ["post-miss"]
        req = urllib.request.Request(
            f"{notify.API}/repos/{repo}/issues", data=json.dumps(fields).encode(), method="POST",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                     "User-Agent": "govallecito-bot"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())

    try:
        try:
            issue = _post(True)
        except urllib.error.HTTPError as exc:
            if exc.code != 422:      # 422 = the label does not exist yet: file it unlabelled
                raise
            issue = _post(False)
        print(f"[post_miss] opened issue #{issue.get('number')}: {title}")
        return {"notified": True, "issue": issue.get("number")}
    except Exception as exc:  # noqa: BLE001 -- an alarm must never take the post path down
        print(f"[post_miss] could not open issue: {exc}")
        return {"notified": False, "reason": str(exc)}


def report_if_needed(now, main, history=None):
    """Open one issue per missed (date, slot) not yet reported. Returns the list of
    (date, slot) it reported. Never raises."""
    try:
        if _dry_run():
            return []
        history = history if history is not None else main.post_history.load_history()
        todo = missed_slots(now, main, history)
        if not todo:
            return []
        state = generate_post_text._load_daily_post_state()
        reported = state.get(STATE_KEY) or {}
        misses = week_of_misses(now, main, history)
        done = []
        for date_iso, slot in todo:
            if slot in (reported.get(date_iso) or []):
                continue
            title = f"[miss] no {slot} conditions post for {date_iso}"
            print(f"MISS: {title}")
            result = _open_issue(title, _body(date_iso, slot, main.SLOT_WINDOWS[slot], misses))
            if result.get("notified"):
                reported.setdefault(date_iso, []).append(slot)
                done.append((date_iso, slot))
        if done:
            cutoff = (now - timedelta(days=KEEP_DAYS)).date().isoformat()
            state[STATE_KEY] = {d: s for d, s in reported.items() if d >= cutoff}
            generate_post_text._save_daily_post_state(state)
        return done
    except Exception as exc:  # noqa: BLE001
        print(f"[post_miss] skipped: {exc}")
        return []
