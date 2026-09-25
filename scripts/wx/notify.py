"""
Getting a held draft in front of a human.

THE GAP THIS CLOSES: guardrails can hold a post for review, but until now
"review" meant writing a file into output/ inside a GitHub Actions run that
nobody opens. A review gate nobody sees is not a safety mechanism, it is just a
way of silently not posting.

A GitHub Issue is the notification channel here, and that is a deliberate
choice over email or a push service: it needs no new account, no new secret
(GITHUB_TOKEN is already present in every Actions run), it emails you
automatically because you own the repo, it is readable and approvable from a
phone, and the issue thread becomes a durable record of every draft that was
held and why -- which is exactly the log you want when tuning the persona.

The draft is posted in full so it can be read without downloading an artifact.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"

# The POST is retried because a lost notification used to be permanent: the
# ledger had already spent the day, so no later run tried again.
NOTIFY_ATTEMPTS = 3
NOTIFY_BACKOFF_S = (3, 8)   # waited before attempt 2, then before attempt 3


def _repo():
    return os.environ.get("GITHUB_REPOSITORY")


def _token():
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def _print_body(body):
    """Print the issue body without letting an encoding fault eat the draft.

    This printing exists so a draft survives a failed notification, so it is
    the one place that must not itself raise on a console that is not UTF-8.
    """
    try:
        print(body)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        print(body.encode(enc, "replace").decode(enc, "replace"))


def _open_issue_titled(repo, token, title):
    """An already-open issue with exactly this title, or None.

    Two things can now aim a second POST at one morning: the retry loop below,
    firing seconds after a request that reached GitHub but whose response was
    lost, and a later run inside the same window retrying a notification that
    failed. Neither may file a duplicate.

    The plain issues list is used rather than the search API because search is
    eventually consistent and this check has to see a write that is seconds
    old.
    """
    req = urllib.request.Request(
        f"{API}/repos/{repo}/issues?state=open&per_page=100",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "govallecito-wx"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            items = json.loads(resp.read().decode())
    except Exception as exc:  # noqa: BLE001 -- a failed check must not block it
        print(f"[notify] could not list open issues ({exc}); not deduping")
        return None
    for item in items or []:
        if item.get("pull_request"):
            continue            # the issues endpoint returns PRs too
        if item.get("title") == title:
            return item
    return None


def review_requested(draft, verdict, reasons, bundle, slot="school_call"):
    """Open an issue with the held draft. Returns a result dict, never raises.

    Notification failure must not take down the forecaster from inside here:
    this function stays quiet and reports. What changed is that the CALLER now
    reads the result. On 2026-09-16 and 09-17 no review issue opened at all and
    both runs still exited 0, because the failure was reported only in a return
    value nobody checked, and in a log that `tee` truncated 56 times a day.

    Three things make that recoverable now: the POST is retried, a final
    failure prints the whole draft so it does not go down with the run, and an
    existing issue with the same title is reused rather than duplicated.
    """
    repo, token = _repo(), _token()
    body = _body(draft, verdict, reasons, bundle, slot)

    if not repo or not token:
        print("=" * 66)
        print(f"REVIEW NEEDED ({verdict}) -- no GitHub context, printing instead")
        print("=" * 66)
        _print_body(body)
        return {"notified": False, "reason": "no GITHUB_REPOSITORY/GITHUB_TOKEN"}

    snow = bundle.get("snow_line") or {}
    sl = snow.get("representative_ft")
    # post_for_date, not local_date. An evening run composes tomorrow's post,
    # so labelling the issue with the run date filed the 2026-08-31 school call
    # under 2026-08-30 and made the drafts folder and the issue list disagree.
    for_date = bundle.get("post_for_date") or bundle.get("local_date")
    title = f"[{verdict}] {slot} draft for {for_date}"
    # Not when it sits above the terrain. The post is forbidden from stating
    # that number, and the issue list must not become the one place it survives.
    if sl and not snow.get("above_terrain"):
        title += f" (snow line ~{sl} ft)"

    def _post(with_labels):
        fields = {"title": title, "body": body}
        if with_labels:
            fields["labels"] = ["wx-review", f"wx-{verdict}"]
        req = urllib.request.Request(
            f"{API}/repos/{repo}/issues", data=json.dumps(fields).encode(),
            method="POST",
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github+json",
                     "User-Agent": "govallecito-wx"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())

    reason = "unknown"
    for attempt in range(1, NOTIFY_ATTEMPTS + 1):
        already = _open_issue_titled(repo, token, title)
        if already:
            print(f"[notify] an issue for this draft is already open: "
                  f"{already.get('html_url')}")
            return {"notified": True, "url": already.get("html_url"),
                    "issue": already.get("number"), "deduped": True}
        try:
            try:
                issue = _post(True)
            except urllib.error.HTTPError as exc:
                # GitHub rejects labels that do not exist yet rather than
                # creating them. The notification matters more than the tidy
                # label, so drop them and retry rather than losing the draft.
                if exc.code == 422:
                    print("[notify] labels do not exist in this repo; retrying without")
                    issue = _post(False)
                else:
                    raise
            print(f"Review issue opened: {issue.get('html_url')}")
            return {"notified": True, "url": issue.get("html_url"),
                    "issue": issue.get("number")}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            reason = f"HTTP {exc.code}"
            print(f"[notify] attempt {attempt}/{NOTIFY_ATTEMPTS}: could not open "
                  f"issue (HTTP {exc.code}): {detail}")
            if exc.code in (401, 404):
                print("[notify] check Settings > Actions > Workflow permissions is "
                      "'Read and write' -- same setting the state commit-back needs.")
        except Exception as exc:  # noqa: BLE001
            reason = str(exc)
            print(f"[notify] attempt {attempt}/{NOTIFY_ATTEMPTS}: could not open "
                  f"issue: {exc}")
        if attempt < NOTIFY_ATTEMPTS:
            # Indexed defensively: raising NOTIFY_ATTEMPTS without extending
            # the tuple would otherwise throw IndexError out of a function
            # whose contract is that it never raises.
            time.sleep(NOTIFY_BACKOFF_S[min(attempt - 1, len(NOTIFY_BACKOFF_S) - 1)])

    print("=" * 66)
    print(f"REVIEW NEEDED ({verdict}) -- NO ISSUE WAS OPENED ({reason})")
    print("=" * 66)
    _print_body(body)
    return {"notified": False, "reason": reason}


def _body(draft, verdict, reasons, bundle, slot):
    L = [f"**Verdict:** `{verdict}`  |  **Slot:** `{slot}`  |  "
         f"**Date:** {bundle.get('local_date')}", ""]
    L.append("### Why it was held")
    for r in reasons:
        L.append(f"- {r}")
    L.append("")

    alerts = bundle.get("alerts") or []
    if alerts:
        L.append("### Active alerts")
        for a in alerts:
            L.append(f"- **{a['event']}** ({', '.join(a.get('zones', []))}), "
                     f"expires {a.get('expires')}")
        L.append("")

    sl = bundle.get("snow_line")
    if sl:
        L.append(f"### Snow line\n`{sl['representative_ft']} ft`, {sl['trend']} "
                 f"({sl['start_ft']} -> {sl['end_ft']} ft)\n")

    dis = bundle.get("model_disagreement")
    if dis:
        L.append(f"### Model spread: {dis['level']} (judged on {dis['basis']})\n"
                 f"Liquid inches: `{dis['all_liquid']}`\n\n"
                 f"Snow inches: `{dis['all_snow']}`\n")

    if bundle.get("missing"):
        L.append(f"### Missing data\n`{bundle['missing']}`\n")

    L.append("### The draft\n")
    L.append("```")
    L.append(draft.strip())
    L.append("```")
    L.append("")
    L.append("---")
    L.append("To publish: paste it to the page yourself, or re-run the workflow "
             "with the reason resolved. Close this issue either way so the "
             "review log stays meaningful.")
    return "\n".join(L)


def miss_reported(slot, date_iso, streak=None):
    """Open an issue saying a scheduled post did NOT happen.

    The counterpart to review_requested. That one fires when a draft exists and
    needs a human; this one fires when no draft exists at all, which was the
    failure mode nobody saw for a week because it produced no error, no red X
    and no output of any kind.
    """
    streak = streak or [date_iso]
    repo, token = _repo(), _token()
    lines = [
        f"No `{slot}` post went out for **{date_iso}**.",
        "",
        "The posting window closed with no draft in `state/drafts/`. That means",
        "either no scheduled run executed inside the window, or every run that",
        "did execute aborted before composing.",
        "",
        "**Where to look, in order:**",
        "",
        "1. `state/last-run-forecast.log`, the last run's own output. If it says",
        "   `outside every posting window`, no run landed inside it and this is a",
        "   GitHub scheduling drop, not a code fault.",
        "2. `state/forecast-status.md`, if it says `aborted, data unavailable`,",
        "   a source was down and `Missing sources` names which one.",
        "3. `state/selftest-latest.md`, which endpoints were reachable.",
        "",
    ]
    if len(streak) > 1:
        lines += [
            f"**This is {len(streak)} misses in the last week:** "
            + ", ".join(streak),
            "",
            "More than one in a week is a pattern, not bad luck. Widening the",
            "posting window or adding cron entries is the lever.",
            "",
        ]
    body = "\n".join(lines)
    title = f"[miss] no {slot} went out for {date_iso}"

    if not repo or not token:
        print("=" * 66)
        print(title)
        print("=" * 66)
        print(body)
        return {"notified": False, "reason": "no GITHUB_REPOSITORY/GITHUB_TOKEN"}

    def _post(with_labels):
        fields = {"title": title, "body": body}
        if with_labels:
            fields["labels"] = ["wx-miss"]
        req = urllib.request.Request(
            f"{API}/repos/{repo}/issues", data=json.dumps(fields).encode(),
            method="POST",
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github+json",
                     "User-Agent": "govallecito-wx"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())

    try:
        try:
            issue = _post(True)
        except urllib.error.HTTPError as exc:
            if exc.code == 422:
                issue = _post(False)
            else:
                raise
        print(f"[notify] opened miss issue #{issue.get('number')}")
        return {"notified": True, "issue": issue.get("number")}
    except Exception as exc:  # noqa: BLE001
        print(f"[notify] could not open miss issue: {exc}")
        return {"notified": False, "reason": str(exc)}
