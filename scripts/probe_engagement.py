"""
ONE-OFF DIAGNOSTIC. Read-only. Delete this file and its workflow once the
engagement fix lands.

Why it exists: every check_engagement.py call since 2026-07-26 has failed with
Graph error #10 ("requires the 'pages_read_engagement' permission"), yet the
SAME FB_PAGE_ACCESS_TOKEN passes fb_preflight.py, whose scopes include
pages_read_engagement and which reads /{page}/published_posts fine. So the
token has the permission and something about the specific request is
rejected. This script asks one real post the same question several ways and
prints only the outcome of each, so one run separates the suspects:

  - auth transport: Authorization: Bearer header (what check_engagement does)
    vs access_token parameter (what fb_preflight does)
  - which field trips it: likes / comments / shares / reactions, alone
  - node read (/{post-id}) vs edge read (/{page-id}/published_posts)

Safety: GET requests only. Never posts, never writes state/. Prints error
codes/messages and integer counts only -- never the token, never the names
of people who liked or commented (every likes/comments read uses limit(0),
so only the summary comes back). Exceptions print their type, not their
text, because a requests exception can embed the full URL and the URL can
carry the token.
"""

import json
import os
import sys

import requests

GRAPH = "https://graph.facebook.com/v25.0"
HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY = os.path.join(os.path.dirname(HERE), "state", "post_history.json")

EXACT = "likes.summary(true),comments.summary(true),shares"  # check_engagement.py's fields


def counts(obj):
    """Reduce a successful Graph payload to integers only."""
    out = {}
    if not isinstance(obj, dict):
        return out
    for key, val in obj.items():
        if key == "id":
            out["id"] = "ok"
        elif isinstance(val, dict) and "summary" in val:
            summ = val.get("summary") or {}
            out[key] = summ.get("total_count")
        elif isinstance(val, dict) and "count" in val:
            out[key] = val.get("count")
        elif isinstance(val, dict) and "data" in val:
            out[key] = f"data[{len(val.get('data') or [])}]"
        elif isinstance(val, list):
            out[key] = f"list[{len(val)}]"
        elif isinstance(val, (int, float)):
            out[key] = val
        else:
            out[key] = type(val).__name__
    return out


def call(label, path, params, token, transport):
    params = dict(params)
    headers = {}
    if transport == "bearer":
        headers["Authorization"] = f"Bearer {token}"
    else:
        params["access_token"] = token
    try:
        resp = requests.get(f"{GRAPH}/{path}", params=params, headers=headers, timeout=20)
        try:
            body = resp.json()
        except ValueError:
            body = {}
    except Exception as exc:  # noqa: BLE001 -- type only, see docstring
        print(f"  {label:<44} [{transport:6}] NETWORK {type(exc).__name__}")
        return
    err = body.get("error") if isinstance(body, dict) else None
    if resp.status_code >= 400 or err:
        err = err or {}
        print(f"  {label:<44} [{transport:6}] FAIL http={resp.status_code} "
              f"code={err.get('code')} sub={err.get('error_subcode')} "
              f"type={err.get('type')} :: {str(err.get('message'))[:170]}")
        return
    if "data" in body and isinstance(body["data"], list) and path.endswith("/insights"):
        summary = {"insights_entries": len(body["data"])}
    elif "data" in body and isinstance(body["data"], list):
        summary = {"rows": len(body["data"]), "first": counts(body["data"][0]) if body["data"] else None}
    else:
        summary = counts(body)
    print(f"  {label:<44} [{transport:6}] OK   {json.dumps(summary)}")


def main():
    token = os.environ.get("FB_PAGE_ACCESS_TOKEN")
    if not token:
        print("FB_PAGE_ACCESS_TOKEN not set")
        return 1
    posts = json.load(open(HISTORY))["posts"]
    daily = [p for p in posts if p.get("post_type", "daily") == "daily" and p.get("post_id")]
    targets = [("oldest daily post", daily[0]), ("a recent written-off post",
               [p for p in daily if p.get("engagement_unavailable")][-1])]
    page_id = daily[0]["post_id"].split("_")[0]

    print("== token identity (same check fb_preflight makes) ==")
    call("/me?fields=id", "me", {"fields": "id"}, token, "param")
    call("/me?fields=id", "me", {"fields": "id"}, token, "bearer")

    for name, post in targets:
        pid = post["post_id"]
        print(f"\n== {name}: posted {post['posted_at'][:10]}, had_image={post.get('had_image')} ==")
        for transport in ("bearer", "param"):
            call("node: id,created_time", pid, {"fields": "id,created_time"}, token, transport)
            call("node: EXACT check_engagement fields", pid,
                 {"fields": "likes.summary(true).limit(0),comments.summary(true).limit(0),shares"},
                 token, transport)
        for label, fields in (
            ("node: shares", "shares"),
            ("node: likes.summary(true).limit(0)", "likes.summary(true).limit(0)"),
            ("node: comments.summary(true).limit(0)", "comments.summary(true).limit(0)"),
            ("node: reactions.summary(total_count).limit(0)", "reactions.summary(total_count).limit(0)"),
        ):
            call(label, pid, {"fields": fields}, token, "param")
        call("edge: /{post}/reactions?summary=total_count", f"{pid}/reactions",
             {"summary": "total_count", "limit": 0}, token, "param")
        call("edge: /{post}/insights post_impressions", f"{pid}/insights",
             {"metric": "post_impressions", "period": "lifetime"}, token, "param")

    print("\n== page edge read (the path fb_preflight proves works) ==")
    for label, fields in (
        ("published_posts: id", "id"),
        ("published_posts: shares", "id,shares"),
        ("published_posts: reactions", "id,reactions.summary(total_count).limit(0)"),
        ("published_posts: likes", "id,likes.summary(true).limit(0)"),
        ("published_posts: comments", "id,comments.summary(true).limit(0)"),
    ):
        call(label, f"{page_id}/published_posts", {"fields": fields, "limit": 3}, token, "param")
    # Sanity: does the exact original (no limit(0)) string even matter? Only
    # its counts are printed, never the people in the lists.
    print("\n(reference) check_engagement.py sends:", EXACT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
