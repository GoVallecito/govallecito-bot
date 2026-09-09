"""
Publishing forecasts to govallecito.com without a cross-repo token.

THE PROBLEM THIS SOLVES. The forecaster lives in GoVallecito/govallecito-bot.
The website lives in a different repository. publish.write_site_post wrote a
markdown file into `WX_SITE_DIR`, which resolves inside the bot's own Actions
checkout, and that checkout is deleted when the job ends. Setting the variable
published a forecast into a container that was then thrown away. The site
integration was never one config flip away; there was no path between the two
repos at all.

The two obvious paths both cost something:

  1. Have the forecast workflow check out the site repo and push into it. That
     needs a personal access token with write access to a second repository,
     stored as a secret in the first. It is the largest new credential surface
     this project would have, and it is the exact thing that has already been
     revoked once.

  2. Have the site's build pull from the bot repo. No token, because the bot
     repo is public, but the naive version means the site build walks a
     directory listing over the API and makes one request per post, against a
     60-per-hour unauthenticated rate limit shared by every build runner on
     that IP.

This module takes the second path and removes its cost. Every run rewrites a
single `feed.json` containing the full text and front matter of every recent
forecast. The site build makes ONE unauthenticated request to
raw.githubusercontent.com and has everything it needs to generate a page per
forecast. No token, no secret, no rate limit, no N+1.

The individual .md files are still written and committed. feed.json is the
transport; the markdown is the durable record, readable in a diff, and what
you would keep if the site were ever rebuilt on something else.

WHY THE FEED IS CAPPED. A year of twice-daily posts is a 3MB JSON file that
every build downloads. The cap keeps the transport small; the .md files keep
the history complete. If the archive ever needs to reach past the cap, it
reads the markdown directly rather than growing the feed.
"""

import json
import os
import re

from . import constants as C

FEED_NAME = "feed.json"
FEED_LIMIT = 120

# Where the site fetches from. Public repo, so no credentials are involved.
RAW_BASE = ("https://raw.githubusercontent.com/GoVallecito/govallecito-bot/"
            "main/site/weather")


def site_dir():
    """The directory the forecaster writes site content into.

    Defaults to a path INSIDE the bot repo, deliberately. The workflow commits
    it like it commits state/, so publishing is a push to a repo we already
    have write access to rather than a cross-repo credential.
    """
    return os.environ.get("WX_SITE_DIR") or os.path.join("site", "weather")


def slugify(s, limit=60):
    # Thousands separators come out of titles before anything else, or
    # "Snow line near 11,200 ft" becomes the URL .../snow-line-near-11-200-ft,
    # which reads as a broken number and splits the keyword.
    s = re.sub(r"(?<=\d),(?=\d)", "", s or "")
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:limit].rstrip("-") or "forecast"


def auto_title(bundle, post_type):
    """A title that reads as a headline and carries the searchable number.

    No em dashes. These become page titles and <title> tags, and the rule
    against machine-looking punctuation applies to the chrome as much as the
    prose.
    """
    sl = bundle.get("snow_line") or {}
    alerts = bundle.get("alerts") or []
    if alerts:
        return f"{alerts[0]['event']} for Vallecito, Bayfield and Durango"
    if sl.get("representative_ft"):
        # Grouped, because this becomes a page title and a headline: "Snow line
        # near 11,200 ft" reads; "near 11200 ft" reads like a serial number.
        return f"Snow line near {int(sl['representative_ft']):,} ft"
    return {
        "school_call": "Morning forecast for Vallecito, Bayfield and Durango",
        "evening": "Evening look at the next few days",
        "storm_setup": "Storm setup for the Vallecito area",
        "totals": "What actually fell",
        "life_safety": "Conditions you need to know about",
    }.get(post_type, "Vallecito area forecast")


def front_matter(bundle, post_type, title):
    sl = bundle.get("snow_line") or {}
    return {
        "title": title,
        "date": bundle.get("generated_at"),
        "forDate": bundle.get("post_for_date") or bundle.get("local_date"),
        "postType": post_type,
        "snowLineFt": sl.get("representative_ft"),
        "snowLineTrend": sl.get("trend"),
        "bands": {k: {"elevationFt": v.get("elevation_ft"),
                      "precipType": v.get("precip_type"),
                      "label": v.get("label")}
                  for k, v in (bundle.get("precip_type_by_band") or {}).items()},
        "basinPercentOfMedian": (bundle.get("basin") or {}).get("pct_of_median"),
        "alerts": [a["event"] for a in (bundle.get("alerts") or [])],
        "sources": sorted({(v or {}).get("source") for v in
                           (bundle.get("sources") or {}).values()
                           if (v or {}).get("source")}),
        "generatedBy": "govallecito-wx",
    }


def write_post(text, bundle, post_type="school_call", title=None, out_dir=None):
    """Write one forecast as markdown with JSON-valued front matter."""
    out_dir = out_dir or site_dir()
    date = (bundle.get("post_for_date") or bundle.get("local_date")
            or C.local_date().isoformat())
    title = title or auto_title(bundle, post_type)
    slug = f"{date}-{slugify(title)}"

    fm = front_matter(bundle, post_type, title)
    fm["slug"] = slug

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


def read_post(path):
    """Parse a post written by write_post back into {front matter, body}.

    Round-tripping through this module rather than a YAML library keeps the
    format honest: if write_post ever emits something read_post cannot read,
    the feed test fails immediately instead of the site silently losing a post.
    """
    with open(path) as fh:
        raw = fh.read()
    if not raw.startswith("---"):
        return None
    try:
        _, fm_block, body = raw.split("---", 2)
    except ValueError:
        return None
    out = {}
    for line in fm_block.strip().splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        try:
            out[k.strip()] = json.loads(v.strip())
        except ValueError:
            out[k.strip()] = v.strip()
    out["body"] = body.strip()
    out.setdefault("slug", os.path.basename(path)[:-3])
    return out


def rebuild_feed(out_dir=None, limit=FEED_LIMIT):
    """Regenerate feed.json from whatever markdown is on disk.

    Rebuilt from the directory rather than appended to, so every way a post can
    arrive here converges on the same result: a normal publish, a held draft
    promoted later by hand, a post edited or deleted in the repo. There is one
    source of truth and it is the files.
    """
    out_dir = out_dir or site_dir()
    posts = []
    if os.path.isdir(out_dir):
        for name in sorted(os.listdir(out_dir), reverse=True):
            if not name.endswith(".md"):
                continue
            post = read_post(os.path.join(out_dir, name))
            if post:
                posts.append(post)
    posts.sort(key=lambda p: (p.get("forDate") or "", p.get("date") or ""),
               reverse=True)
    feed = {
        "generatedAt": C.local_now().isoformat(timespec="seconds"),
        "count": len(posts),
        "truncated": len(posts) > limit,
        "posts": posts[:limit],
    }
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, FEED_NAME)
    with open(path, "w") as fh:
        json.dump(feed, fh, indent=2, sort_keys=False)
    return path


def publish(text, bundle, post_type="school_call", title=None, out_dir=None):
    """Write the post and refresh the feed. Returns both paths."""
    out_dir = out_dir or site_dir()
    post_path = write_post(text, bundle, post_type, title, out_dir)
    feed_path = rebuild_feed(out_dir)
    return {"post": post_path, "feed": feed_path}


# --- the approval path -----------------------------------------------------
#
# Every draft so far has been held for review, and there was no way to act on
# that review other than switching the gate off for everything at once. That
# makes going live an all-or-nothing event: the website and the Facebook page
# would start publishing in the same minute, on the same untested verdict.
#
# Staging decouples them. A held draft is written, fully formed and with its
# front matter intact, into a _pending directory that the feed ignores. Reading
# it and deciding it is good is then a one-command promotion, with no bundle to
# reconstruct and no model call to repeat. The website can go live weeks before
# the Facebook page does, which is the right order: the site has no audience
# yet and every published page compounds into search.

PENDING = "_pending"


def pending_dir(out_dir=None):
    return os.path.join(out_dir or site_dir(), PENDING)


def stage(text, bundle, post_type="school_call", title=None, out_dir=None):
    """Write a held draft where it can be promoted later without recomposing."""
    return write_post(text, bundle, post_type, title, pending_dir(out_dir))


def list_pending(out_dir=None):
    d = pending_dir(out_dir)
    if not os.path.isdir(d):
        return []
    return sorted((n for n in os.listdir(d) if n.endswith(".md")), reverse=True)


def promote(date_or_slug, out_dir=None):
    """Move a staged post into the live directory and refresh the feed.

    Accepts a full slug or just a date, because the date is what a person has
    in front of them when they are reading a review issue.
    """
    out_dir = out_dir or site_dir()
    src_dir = pending_dir(out_dir)
    names = [n for n in list_pending(out_dir) if n.startswith(date_or_slug)]
    if not names:
        raise FileNotFoundError(
            f"nothing staged matching {date_or_slug!r} in {src_dir}. "
            f"Available: {list_pending(out_dir) or 'none'}")
    if len(names) > 1:
        raise ValueError(f"{date_or_slug!r} matches {len(names)} staged posts "
                         f"({names}); name one exactly.")
    name = names[0]
    os.makedirs(out_dir, exist_ok=True)
    dest = os.path.join(out_dir, name)
    os.replace(os.path.join(src_dir, name), dest)
    return {"post": dest, "feed": rebuild_feed(out_dir)}
