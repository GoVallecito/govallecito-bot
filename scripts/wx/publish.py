"""
Publishing. Reuses the existing bot's proven Facebook path wherever possible.

THREE DESTINATIONS, in order of importance:

  1. govallecito.com  -- an Astro content file committed to the site repo. This
     is the durable one. Facebook posts vanish into a feed; a dated page at
     /weather/2026-11-04-... is indexed, linkable, and is the strongest SEO
     asset a local site can have. It also mirrors how the model persona works:
     website of record, Facebook for distribution.

  2. The Facebook PAGE -- text post, not a photo post. The existing conditions
     bot posts 1080x1080 cards because a conditions card IS an image. A
     forecast is 300 words of prose that must not be squeezed to fit a card, so
     this uses /feed rather than /photos.

  3. The Facebook GROUP -- the same content shared with a one-line human
     caption, which is exactly the pattern the model persona uses. Note the
     honest caveat in post_to_group().

DRY_RUN is respected identically to the existing bot: same env var, same
semantics, same "empty string counts as true" handling, so one repo variable
governs everything.
"""

import datetime as _dt
import json
import os
import re
import urllib.parse
import urllib.request

GRAPH_VERSION = "v25.0"
DEFAULT_PAGE_ID = "1138532512682553"   # GoVallecito Page -- public, not a secret


def is_dry_run():
    # Matches the existing bot exactly: GitHub Actions sets an unconfigured
    # variable to "" (present, not unset), which .get()'s default would miss.
    raw = (os.environ.get("DRY_RUN") or "true").strip().lower()
    return raw not in ("false", "0", "no")


def _graph_post(path, fields):
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{path}"
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def post_to_page(text, page_id=None, token=None, link=None):
    page_id = page_id or os.environ.get("FB_PAGE_ID") or DEFAULT_PAGE_ID
    token = token or os.environ.get("FB_PAGE_ACCESS_TOKEN")

    if is_dry_run():
        return _dry("page", text, page_id)
    if not token:
        raise RuntimeError("FB_PAGE_ACCESS_TOKEN is not set")

    fields = {"message": text, "access_token": token}
    if link:
        fields["link"] = link
    try:
        payload = _graph_post(f"{page_id}/feed", fields)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Facebook page post failed: {exc}") from exc
    if "error" in payload:
        raise RuntimeError(f"Facebook error: {payload['error']}")
    return payload


def post_photo_to_page(text, image_path, page_id=None, token=None):
    """Post the elevation card WITH the forecast text as its caption.

    Preferred over post_to_page() whenever a card rendered. A weather post with
    a graphic travels; a wall of text does not. Uses multipart/form-data via
    the /photos edge, the same edge the existing conditions bot uses.
    """
    import mimetypes
    import uuid

    page_id = page_id or os.environ.get("FB_PAGE_ID") or DEFAULT_PAGE_ID
    token = token or os.environ.get("FB_PAGE_ACCESS_TOKEN")

    if is_dry_run():
        res = _dry("page-photo", text, page_id)
        res["image"] = image_path
        return res
    if not token:
        raise RuntimeError("FB_PAGE_ACCESS_TOKEN is not set")

    boundary = uuid.uuid4().hex
    with open(image_path, "rb") as fh:
        blob = fh.read()
    ctype = mimetypes.guess_type(image_path)[0] or "image/png"

    parts = []
    for name, value in (("caption", text), ("access_token", token)):
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
            f"{value}\r\n".encode())
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"source\"; "
        f"filename=\"{os.path.basename(image_path)}\"\r\n"
        f"Content-Type: {ctype}\r\n\r\n".encode())
    parts.append(blob)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)

    req = urllib.request.Request(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{page_id}/photos",
        data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Facebook photo post failed: {exc}") from exc
    if "error" in payload:
        raise RuntimeError(f"Facebook error: {payload['error']}")
    return payload


def post_to_group(text, group_id=None, token=None):
    """Share into the Facebook Group.

    HONEST CAVEAT, do not skip this: Meta deprecated the Groups API publishing
    permission for most apps, so programmatic group posting may simply not be
    available on this account. Treat a failure here as expected, not as a bug,
    and fall back to the manual share -- which takes about eight seconds and is
    what the model persona appears to do anyway (his group posts carry a short
    hand-written caption above the shared page post, which is a human touch
    worth keeping regardless).
    """
    group_id = group_id or os.environ.get("FB_GROUP_ID")
    token = token or os.environ.get("FB_PAGE_ACCESS_TOKEN")
    if not group_id:
        return {"skipped": "no FB_GROUP_ID configured"}
    if is_dry_run():
        return _dry("group", text, group_id)
    try:
        return _graph_post(f"{group_id}/feed", {"message": text, "access_token": token})
    except Exception as exc:  # noqa: BLE001
        return {"failed": str(exc),
                "note": "Group publishing is restricted by Meta; share manually."}


def _dry(target, text, ident):
    os.makedirs("output", exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = os.path.join("output", f"{stamp}_{target}.txt")
    with open(path, "w") as fh:
        fh.write(text)
    print("=" * 66)
    print(f"DRY RUN -- nothing posted. Target: {target} {ident}")
    print("-" * 66)
    print(text)
    print("-" * 66)
    print(f"Saved to {path}")
    print("=" * 66)
    return {"dry_run": True, "target": target, "path": path}


def slugify(s, limit=60):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:limit].rstrip("-")


def write_site_post(text, bundle, out_dir, post_type="school_call", title=None):
    """Write an Astro content-collection markdown file for govallecito.com.

    Front matter is deliberately rich: the snow line, the band breakdown and
    the source list are all queryable, so the site can render a conditions
    table, an archive, and a public track-record page from the same files
    without re-parsing prose.
    """
    date = bundle.get("local_date") or _dt.date.today().isoformat()
    sl = bundle.get("snow_line") or {}
    title = title or _auto_title(bundle, post_type)
    slug = f"{date}-{slugify(title)}"

    fm = {
        "title": title,
        "date": bundle.get("generated_at"),
        "postType": post_type,
        "snowLineFt": sl.get("representative_ft"),
        "snowLineTrend": sl.get("trend"),
        "bands": {k: {"elevationFt": v.get("elevation_ft"),
                      "precipType": v.get("precip_type")}
                  for k, v in (bundle.get("precip_type_by_band") or {}).items()},
        "basinPercentOfMedian": (bundle.get("basin") or {}).get("pct_of_median"),
        "alerts": [a["event"] for a in (bundle.get("alerts") or [])],
        "sources": sorted({(v or {}).get("source") for v in
                           (bundle.get("sources") or {}).values()
                           if (v or {}).get("source")}),
        "generatedBy": "govallecito-wx",
    }

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{slug}.md")
    with open(path, "w") as fh:
        fh.write("---\n")
        for k, v in fm.items():
            fh.write(f"{k}: {json.dumps(v)}\n")
        fh.write("---\n\n")
        fh.write(text.strip())
        fh.write("\n")
    return path


def _auto_title(bundle, post_type):
    sl = bundle.get("snow_line") or {}
    alerts = bundle.get("alerts") or []
    if alerts:
        return f"{alerts[0]['event']} — Vallecito, Bayfield and Durango"
    if sl.get("representative_ft"):
        return f"Snow line near {sl['representative_ft']} ft — the morning call"
    return {"school_call": "Morning forecast — Vallecito, Bayfield, Durango",
            "evening": "Evening look — the next few days",
            "totals": "What actually fell",
            }.get(post_type, "Vallecito area forecast")
