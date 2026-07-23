"""
Finds and downloads a real, safely-licensed photo from Wikimedia Commons for
the "grounded" seasonal posts (see config/seasonal_almanac.json).

*** NOT CONFIRMED LIVE -- READ THIS BEFORE TRUSTING IT ***
The sandbox that wrote this code has no path to the internet at all beyond a
small package-registry allowlist -- confirmed directly: WebFetch on Commons'
own API returned "cache-only, cannot be fetched," and a raw curl to
commons.wikimedia.org, upload.wikimedia.org, nps.gov, and digitalmedia.fws.gov
all came back as connection failures. So unlike fetch_conditions.py (where at
least the *endpoints* were confirmed reachable even if some field names
weren't), this file could not be exercised against the real API even once.
The query shape below matches Wikimedia's long-stable, well-documented
MediaWiki API conventions (generator=categorymembers + imageinfo/extmetadata
is a standard, widely-used pattern) -- but "should be right based on how this
API has worked for years" is not the same as "confirmed."

Given that, this fails CLOSED by design: if anything about the response is
unexpected, or no candidate image's license can be positively confirmed
safe, this returns None and the caller falls back to the plain data card
with no photo. A missing bonus photo is a fine outcome. Posting an image
whose license we guessed wrong is not -- that's a real legal/reputational
risk, not a cosmetic one, so this deliberately does not try to be clever
about borderline cases.

Only images explicitly marked public domain or CC0 are used -- no
attribution-required (CC-BY / CC-BY-SA) images, even though those are also
legally usable with credit. Keeping the bar at "no attribution legally
required" avoids the whole separate problem of generating correct credit
lines automatically. Run scripts/test_data_sources.py-style manual checks
(see README) before trusting this in production.
"""

import os
import random

import requests
from PIL import Image

REQUEST_TIMEOUT = 20
MIN_WIDTH = 800
MIN_HEIGHT = 600

# Only these license signals are trusted. Deliberately conservative --
# CC-BY/CC-BY-SA (attribution required) are excluded even though they're
# legally usable, to avoid needing to auto-generate correct credit lines.
SAFE_LICENSE_SUBSTRINGS = ("public domain", "cc0", "pdm")


def _is_safe_license(extmetadata):
    """extmetadata is the dict Wikimedia's API returns per-image. Returns
    True only if we can positively confirm a safe license; anything
    ambiguous or missing returns False (fail closed). The Restrictions
    check runs FIRST and unconditionally -- a Commons "Restrictions" flag
    (e.g. "insignia", "trademarked") means the file isn't blanket-safe to
    reuse even when it's also technically public domain / CC0, so it must
    be able to veto the other two signals rather than be short-circuited
    by them."""
    try:
        restrictions = extmetadata.get("Restrictions", {}).get("value", "").strip()
        if restrictions:
            return False
        if extmetadata.get("Copyrighted", {}).get("value", "").strip().lower() == "false":
            return True
        license_short = extmetadata.get("LicenseShortName", {}).get("value", "").strip().lower()
        if any(safe in license_short for safe in SAFE_LICENSE_SUBSTRINGS):
            return True
    except Exception:
        return False
    return False


def search_commons_image(commons_category, min_width=MIN_WIDTH, min_height=MIN_HEIGHT):
    """Returns {"url", "title", "license", "page_url", "width", "height"} for
    a randomly-chosen qualifying image in the given Commons category, or
    None if nothing safe/suitable was found (including on any error)."""
    api_url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "categorymembers",
        "gcmtitle": commons_category,
        "gcmtype": "file",
        "gcmlimit": 25,
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata",
        "format": "json",
        "formatversion": 2,
    }
    try:
        resp = requests.get(api_url, params=params, timeout=REQUEST_TIMEOUT,
                             headers={"User-Agent": "govallecito-bot/1.0 (contact@govallecito.com)"})
        resp.raise_for_status()
        data = resp.json()
        pages = data.get("query", {}).get("pages", [])

        candidates = []
        for page in pages:
            try:
                infos = page.get("imageinfo") or []
                if not infos:
                    continue
                info = infos[0]
                width, height = info.get("width", 0), info.get("height", 0)
                if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
                    continue
                if width < min_width or height < min_height:
                    continue
                extmetadata = info.get("extmetadata", {})
                if not isinstance(extmetadata, dict):
                    continue
                if not _is_safe_license(extmetadata):
                    continue
                candidates.append({
                    "url": info.get("url"),
                    "title": page.get("title", ""),
                    "license": extmetadata.get("LicenseShortName", {}).get("value", "public domain"),
                    "page_url": info.get("descriptionurl", ""),
                    "width": width,
                    "height": height,
                })
            except Exception as exc:
                print(f"[search_commons_image] skipping malformed candidate: {exc}")
                continue

        if not candidates:
            print(f"[search_commons_image] no safe/suitable candidates in {commons_category}")
            return None
        return random.choice(candidates)

    except Exception as exc:
        print(f"[search_commons_image] failed for {commons_category}: {exc}")
        return None


def download_image(url, dest_path, timeout=REQUEST_TIMEOUT):
    """Downloads url to dest_path. Returns True on success, False on any
    failure (caller should treat False the same as 'no image available').
    Validates the downloaded file is actually an openable raster image
    before declaring success -- Commons categories can contain non-raster
    files (e.g. SVG range maps) alongside real photos, and those would
    otherwise crash render_card.py downstream with no fallback."""
    try:
        resp = requests.get(url, timeout=timeout,
                             headers={"User-Agent": "govallecito-bot/1.0 (contact@govallecito.com)"})
        resp.raise_for_status()
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(resp.content)
        with Image.open(dest_path) as img:
            img.verify()
        return True
    except Exception as exc:
        print(f"[download_image] failed for {url}: {exc}")
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except OSError:
                pass
        return False


def get_seasonal_image(commons_category, dest_path):
    """Convenience wrapper: search + download in one call. Returns the same
    dict as search_commons_image (with dest_path added) on success, or None
    on any failure -- caller falls back to the no-photo card."""
    result = search_commons_image(commons_category)
    if not result:
        return None
    if not download_image(result["url"], dest_path):
        return None
    result["local_path"] = dest_path
    return result


if __name__ == "__main__":
    import sys
    category = sys.argv[1] if len(sys.argv) > 1 else "Category:Selasphorus rufus"
    result = get_seasonal_image(category, "/tmp/test_commons_image.jpg")
    print(result)
