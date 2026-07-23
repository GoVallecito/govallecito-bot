"""
Posts the rendered card + caption to the Facebook Page via the Graph API.

Reads two things from the environment (GitHub Actions secrets map straight
to env vars):
  FB_PAGE_ACCESS_TOKEN  -- required to actually post. A long-lived Page
                           token obtained via /{user-id}/accounts (see
                           README). Per Meta's own docs, tokens obtained this
                           way "do not have an expiration date and only
                           expire or are invalidated under certain
                           conditions" -- durable, but not a guarantee. If
                           this suddenly starts failing with an auth error,
                           regenerating the token is almost certainly the fix.
  FB_PAGE_ID            -- not actually sensitive (it's public), but kept
                           configurable rather than hardcoded. Defaults to
                           GoVallecito's page id below.

DRY_RUN (env var, default "true"): when true, this does NOT call the Graph
API at all. It writes the image + caption into output/ and prints what it
would have posted, so the whole pipeline can be exercised safely before
anything goes out on the real page. Flip to "false" only once you've watched
a few dry runs come out looking right (see README).
"""

import os
import sys

import requests

GRAPH_API_VERSION = "v25.0"  # bump this if developers.facebook.com/docs/graph-api/changelog shows a newer stable version
DEFAULT_PAGE_ID = "1138532512682553"  # GoVallecito Page -- public info, not a secret


def _is_dry_run():
    # os.environ.get(key, default) only falls back to the default when the
    # key is ABSENT -- GitHub Actions sets DRY_RUN to an empty string
    # (present, not unset) whenever the underlying vars.DRY_RUN repo
    # variable was never configured, which .get()'s own default doesn't
    # catch. Falling back to "true" (safe/dry-run) for an empty value too
    # makes that the explicit, robust behavior rather than an accident of
    # "" happening to not match any of the false-ish strings below.
    raw = (os.environ.get("DRY_RUN") or "true").strip().lower()
    return raw not in ("false", "0", "no")


def post_photo(image_path, caption, page_id=None, access_token=None):
    """Posts image_path with caption as a Facebook Page photo post.
    Returns the Graph API's JSON response on success.
    Raises RuntimeError with a clear message on failure.
    In dry-run mode, returns a fake response and writes to output/ instead.
    """
    # `or` against os.environ.get("FB_PAGE_ID") (no default arg) rather than
    # os.environ.get("FB_PAGE_ID", DEFAULT_PAGE_ID) -- the README calls this
    # env var optional and safe to skip, but GitHub Actions sets it to an
    # empty string (present, not unset) whenever the underlying vars.FB_PAGE_ID
    # repo variable was never configured. .get()'s default only kicks in
    # when the key is absent, so it would silently pass through "" instead
    # of DEFAULT_PAGE_ID, breaking the Graph API URL for anyone who follows
    # the README exactly and skips setting the repo variable.
    page_id = page_id or os.environ.get("FB_PAGE_ID") or DEFAULT_PAGE_ID
    access_token = access_token or os.environ.get("FB_PAGE_ACCESS_TOKEN")

    if _is_dry_run():
        os.makedirs("output", exist_ok=True)
        import shutil
        import time
        stamp = time.strftime("%Y-%m-%d_%H%M%S")
        out_img = os.path.join("output", f"{stamp}.png")
        out_txt = os.path.join("output", f"{stamp}.txt")
        shutil.copy(image_path, out_img)
        with open(out_txt, "w") as f:
            f.write(caption)
        print("=" * 60)
        print("DRY RUN -- nothing was posted to Facebook.")
        print(f"Would have posted to Page {page_id}:")
        print("-" * 60)
        print(caption)
        print("-" * 60)
        print(f"Image and caption saved to {out_img} / {out_txt}")
        print("(GitHub Actions: check this run's 'artifacts' to download and look at them.)")
        print("=" * 60)
        return {"dry_run": True, "id": None}

    if not access_token:
        raise RuntimeError(
            "FB_PAGE_ACCESS_TOKEN is not set. Add it as a GitHub Actions secret "
            "(Settings -> Secrets and variables -> Actions) -- see README."
        )

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/photos"
    try:
        with open(image_path, "rb") as image_file:
            resp = requests.post(
                url,
                data={"caption": caption, "access_token": access_token},
                files={"source": image_file},
                timeout=30,
            )
    except requests.exceptions.RequestException as exc:
        # Network-level failures (DNS, connection refused, timeout, etc.)
        # raise requests' own exception types, not RuntimeError -- but this
        # function's whole contract (see docstring) is "raises RuntimeError
        # on failure." A caller that only catches RuntimeError (reasonably,
        # given that contract) would otherwise see an uncaught crash on a
        # plain network hiccup instead of the same handled-failure path
        # every other failure mode here goes through.
        raise RuntimeError(f"Network error while posting to Facebook: {exc}") from exc

    try:
        payload = resp.json()
    except ValueError:
        raise RuntimeError(f"Facebook returned a non-JSON response (HTTP {resp.status_code}): {resp.text[:500]}")

    if resp.status_code >= 400 or "error" in payload:
        err = payload.get("error", {})
        raise RuntimeError(
            f"Facebook Graph API error (HTTP {resp.status_code}): "
            f"{err.get('message', payload)} [type={err.get('type')}, code={err.get('code')}]"
        )

    print(f"Posted successfully. Post/photo id: {payload.get('id') or payload.get('post_id')}")
    return payload


if __name__ == "__main__":
    # Small manual smoke test: post_to_facebook.py <image_path> "<caption>"
    if len(sys.argv) != 3:
        print("Usage: python post_to_facebook.py <image_path> <caption>")
        sys.exit(1)
    result = post_photo(sys.argv[1], sys.argv[2])
    print(result)
