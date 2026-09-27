"""
Read-only Facebook credential check. GETs only; this can never post.

    python scripts/wx/fb_preflight.py        # exit 0 pass, 1 fail

The facebook-post workflow runs this before every mode, so a bad token is
reported by name before anything tries to use it. It checks:

  1. FB_PAGE_ACCESS_TOKEN is present.
  2. GET /me returns the PAGE. A Page token answers /me as the Page; a personal
     user token answers as a person, and that is the commonest wrong thing to
     paste into the secret. It is caught here by name instead of surfacing as
     an opaque permissions error at 5:45am.
  3. GET /{page_id} for the Page's name and follower count, so the log shows
     which Page is about to be posted to.
  4. GET /{page_id}/published_posts?limit=1, because pages_read_engagement is a
     dependency of pages_manage_posts; a token that cannot read the feed will
     not be able to write to it.
  5. GET /debug_token for scopes and expiry. Best effort: it can be refused
     for reasons that have nothing to do with whether the token can post, so a
     failure there is printed and never fails the check.

An HTTP rejection (Facebook answered, and said no) is told apart from a
network error (Facebook was never reached). Only the first means the token is
bad; telling someone to re-mint a good token over a DNS blip wastes their
morning and teaches them to ignore this check.

The token is never printed.
"""

import datetime as _dt
import json
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wx import publish as P  # noqa: E402

OK, REJECTED, NETWORK = "ok", "rejected", "network"


def _get(path, params):
    """(kind, payload). kind is OK, REJECTED (HTTP error from Graph) or NETWORK."""
    url = (f"https://graph.facebook.com/{P.GRAPH_VERSION}/{path}?"
           + urllib.parse.urlencode(params))
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=20) as resp:
            return OK, json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            body = {}
        err = body.get("error") if isinstance(body, dict) else None
        return REJECTED, {"status": exc.code, "error": err or {"message": str(exc)}}
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
        return NETWORK, {"error": {"message": str(getattr(exc, "reason", exc))}}


def _why(payload):
    err = (payload or {}).get("error") or {}
    msg = err.get("message") or "no message"
    code = err.get("code")
    return f"{msg}" + (f" (code {code})" if code is not None else "")


def run(token=None, page_id=None, get=None, out=print):
    """Returns 0 when the token can post to the Page, 1 otherwise."""
    get = get or _get
    token = token if token is not None else os.environ.get("FB_PAGE_ACCESS_TOKEN")
    page_id = page_id or os.environ.get("FB_PAGE_ID") or P.DEFAULT_PAGE_ID
    auth = {"access_token": token}

    def network(step, payload):
        out(f"FAIL  {step}: could not reach Facebook ({_why(payload)}).")
        out("      This is a network problem, not a token problem. Do NOT "
            "re-mint the token; run the check again.")
        return 1

    if not (token or "").strip():
        out("FAIL  FB_PAGE_ACCESS_TOKEN is not set. Add it as a repository "
            "secret (Settings > Secrets and variables > Actions).")
        return 1
    out(f"ok    token present; target page {page_id}")

    kind, me = get("me", {**auth, "fields": "id,name"})
    if kind == NETWORK:
        return network("GET /me", me)
    if kind == REJECTED:
        out(f"FAIL  GET /me rejected the token: {_why(me)}")
        out("      The token is expired, revoked or malformed. Mint a new "
            "Page access token and replace the secret.")
        return 1
    if str(me.get("id")) != str(page_id):
        out(f"FAIL  the token belongs to {me.get('name')!r} (id {me.get('id')}), "
            f"not page {page_id}.")
        out("      This looks like a personal USER token. The secret needs a "
            "PAGE access token for the GoVallecito Page.")
        return 1
    out(f"ok    /me is the page itself: {me.get('name')!r}")

    kind, page = get(page_id, {**auth, "fields": "name,followers_count"})
    if kind == NETWORK:
        return network(f"GET /{page_id}", page)
    if kind == REJECTED:
        out(f"FAIL  GET /{page_id} rejected: {_why(page)}")
        return 1
    out(f"ok    page {page.get('name')!r}, "
        f"{page.get('followers_count', 'unknown')} followers")

    kind, feed = get(f"{page_id}/published_posts", {**auth, "limit": 1})
    if kind == NETWORK:
        return network(f"GET /{page_id}/published_posts", feed)
    if kind == REJECTED:
        out(f"FAIL  GET /{page_id}/published_posts rejected: {_why(feed)}")
        out("      The token lacks pages_read_engagement, which "
            "pages_manage_posts depends on. Re-mint it with both permissions.")
        return 1
    out("ok    can read the page published posts (pages_read_engagement)")

    # Informational only, from here on nothing can fail the check.
    kind, dbg = get("debug_token", {**auth, "input_token": token})
    data = (dbg or {}).get("data") or {}
    if kind != OK or not data:
        out(f"info  debug_token unavailable ({_why(dbg) if kind != OK else 'no data'}); "
            "scopes and expiry not shown. Not a failure.")
    else:
        scopes = data.get("scopes") or []
        out(f"info  scopes: {', '.join(scopes) or 'none listed'}")
        if scopes and "pages_manage_posts" not in scopes:
            out("warn  pages_manage_posts is not in the scope list; posting "
                "will likely be refused.")
        exp = data.get("expires_at")
        if not exp:
            out("info  expires: never")
        else:
            try:
                when = _dt.datetime.fromtimestamp(int(exp), _dt.timezone.utc)
                out(f"info  expires: {when:%Y-%m-%d %H:%M} UTC")
            except (TypeError, ValueError, OverflowError, OSError):
                out(f"info  expires: {exp}")
    out("PASS  the token can reach and read the GoVallecito Page.")
    return 0


def main():
    sys.exit(run())


if __name__ == "__main__":
    main()
