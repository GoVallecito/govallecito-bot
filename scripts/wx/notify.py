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
import urllib.error
import urllib.request

API = "https://api.github.com"


def _repo():
    return os.environ.get("GITHUB_REPOSITORY")


def _token():
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def review_requested(draft, verdict, reasons, bundle, slot="school_call"):
    """Open an issue with the held draft. Returns a result dict, never raises.

    Notification failure must not take down the forecaster: the post was
    already held, and an exception here would turn "held for review" into
    "workflow failed," which reads as something much worse than it is.
    """
    repo, token = _repo(), _token()
    body = _body(draft, verdict, reasons, bundle, slot)

    if not repo or not token:
        print("=" * 66)
        print(f"REVIEW NEEDED ({verdict}) -- no GitHub context, printing instead")
        print("=" * 66)
        print(body)
        return {"notified": False, "reason": "no GITHUB_REPOSITORY/GITHUB_TOKEN"}

    sl = (bundle.get("snow_line") or {}).get("representative_ft")
    title = f"[{verdict}] {slot} draft — {bundle.get('local_date')}"
    if sl:
        title += f" (snow line ~{sl} ft)"

    payload = json.dumps({
        "title": title,
        "body": body,
        "labels": ["wx-review", f"wx-{verdict}"],
    }).encode()
    req = urllib.request.Request(
        f"{API}/repos/{repo}/issues", data=payload, method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "govallecito-wx"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            issue = json.loads(resp.read().decode())
        print(f"Review issue opened: {issue.get('html_url')}")
        return {"notified": True, "url": issue.get("html_url")}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        print(f"[notify] could not open issue (HTTP {exc.code}): {detail}")
        print("[notify] check Settings > Actions > Workflow permissions is "
              "'Read and write' -- same setting the state commit-back needs.")
        return {"notified": False, "reason": f"HTTP {exc.code}"}
    except Exception as exc:  # noqa: BLE001
        print(f"[notify] could not open issue: {exc}")
        return {"notified": False, "reason": str(exc)}


def _body(draft, verdict, reasons, bundle, slot):
    L = [f"**Verdict:** `{verdict}`  ·  **Slot:** `{slot}`  ·  "
         f"**Date:** {bundle.get('local_date')}", ""]
    L.append("### Why it was held")
    for r in reasons:
        L.append(f"- {r}")
    L.append("")

    alerts = bundle.get("alerts") or []
    if alerts:
        L.append("### Active alerts")
        for a in alerts:
            L.append(f"- **{a['event']}** ({', '.join(a.get('zones', []))}) — "
                     f"expires {a.get('expires')}")
        L.append("")

    sl = bundle.get("snow_line")
    if sl:
        L.append(f"### Snow line\n`{sl['representative_ft']} ft`, {sl['trend']} "
                 f"({sl['start_ft']} → {sl['end_ft']} ft)\n")

    dis = bundle.get("model_disagreement")
    if dis:
        L.append(f"### Model spread: {dis['level']}\n`{dis['all']}`\n")

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
