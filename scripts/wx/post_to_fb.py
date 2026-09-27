"""
Mirror an ALREADY PUBLISHED forecast to the Facebook Page, by hand.

    python scripts/wx/post_to_fb.py                    # dry run, today's school call
    python scripts/wx/post_to_fb.py --date 2026-09-27  # dry run, any date, any hour
    python scripts/wx/post_to_fb.py --live             # actually posts

WHY THIS EXISTS. DRY_RUN is one repo variable gating five posting paths, so it
cannot be flipped to put the morning forecast on Facebook without also
restarting the conditions bot, emergency alerts, the storm watch and the
verification post. This posts exactly one thing, the body of a post that is
already on govallecito.com, and only when a person runs it with --live.

It composes, re-words and re-sanitizes NOTHING. The body in site/weather/ goes
to the Page byte for byte, because the thing reviewed must be the thing
published, and the website is what was reviewed.

SAFETY, in the order it is checked:
  - A held draft (site/weather/_pending/) is refused unless --allow-pending;
    read its panel transcript first, state/panel/<date>-<slot>.md.
  - One Facebook post per slot per day: ledger.flag(date, "fb:<slot>") after a
    successful post, and a second run refuses unless --force.
  - A live post of a date that is not the current one, or of a school call
    after 11:00 (an evening look after 23:00), is refused unless
    --allow-stale. A mistyped date in the workflow form is the likeliest way
    this posts the wrong forecast. Enforced on --live ONLY: a dry run of any
    date at any hour must still work, or the safe mode would be harder to use
    than the dangerous one.
  - Without --live nothing is posted, even when DRY_RUN=false.
  - A Graph reply with no post id is a failure: the day is left UNflagged so
    it can be retried.
"""

import argparse
import datetime as _dt
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wx import constants as C   # noqa: E402
from wx import publish as P     # noqa: E402
from wx import site as SITE     # noqa: E402

# The hour (local) from which a live post of the slot is too late to be useful.
# A school call is written for parents deciding before the districts do at
# 6:30; by 11:00 it is a stale forecast wearing a fresh Facebook timestamp.
STALE_AFTER_HOUR = {"school_call": 11, "evening": 23}


def ledger_name(slot):
    return f"fb:{slot}"


def for_date(now):
    """The date a post composed at `now` is FOR, by the same rule the bundle
    uses: from noon on it is tomorrow's. For a school call inside its useful
    hours this is simply today; for an evening look it is tomorrow."""
    return (now.date() + _dt.timedelta(days=1) if now.hour >= 12
            else now.date()).isoformat()


def _matches(path, slot):
    post = SITE.read_post(path)
    if not post:
        return None
    pt = post.get("postType")
    if pt and pt != slot:
        return None
    return post


def find_post(date, slot="school_call", site_dir=None):
    """(path, body, where) for the slot's post on `date`, or None.

    Published (site/weather/) is searched first and wins over a pending file
    for the same date: a draft that was later promoted can leave a stale copy
    behind, and the published one is what the website shows.
    where is "published" or "pending".
    """
    base = site_dir or SITE.site_dir()
    for where, d in (("published", base), ("pending", SITE.pending_dir(base))):
        hits = []
        for path in sorted(glob.glob(os.path.join(d, f"{date}-*.md"))):
            post = _matches(path, slot)
            if post is not None:
                hits.append((path, post))
        if len(hits) > 1:
            raise LookupError(f"{len(hits)} {where} {slot} posts for {date}: "
                              f"{[os.path.basename(p) for p, _ in hits]}. "
                              "Remove the extra one before mirroring.")
        if hits:
            path, post = hits[0]
            return path, post["body"], where
    return None


def staleness(date, slot, now):
    """A reason a live post of `date` would be stale at `now`, or None."""
    expected = for_date(now)
    if date != expected:
        return (f"{date} is not the current {slot} date ({expected}). A "
                "mistyped date posts the wrong forecast.")
    limit = STALE_AFTER_HOUR.get(slot)
    if limit is not None and now.hour >= limit:
        return (f"it is {now:%H:%M}, past {limit:02d}:00, when a {slot} stops "
                "being useful.")
    return None


def _ledger(injected=None):
    if injected is not None:
        return injected
    from wx import ledger as _lg
    return _lg


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", default="",
                    help="YYYY-MM-DD, default the current post date (America/Denver)")
    ap.add_argument("--slot", default="school_call")
    ap.add_argument("--live", action="store_true",
                    help="actually post. Without this, nothing is posted.")
    ap.add_argument("--force", action="store_true",
                    help="post even though the ledger says this slot already went")
    ap.add_argument("--allow-pending", action="store_true",
                    help="allow a held draft from site/weather/_pending/")
    ap.add_argument("--allow-stale", action="store_true",
                    help="allow a live post of another date or after the cutoff hour")
    return ap.parse_args(argv)


def main(argv=None, now=None, post=None, ledger=None):
    args = parse_args(argv)
    now = now or C.local_now()
    post = post or P.post_to_page
    LG = _ledger(ledger)
    slot = args.slot
    date = (args.date or "").strip() or for_date(now)
    name = ledger_name(slot)

    try:
        found = find_post(date, slot)
    except LookupError as exc:
        print(f"::error::{exc}")
        return 1
    if not found:
        print(f"::error::no {slot} post found for {date} in "
              f"{SITE.site_dir()} or its _pending/ directory.")
        return 1
    path, body, where = found
    print(f"{where} post: {path}")

    if where == "pending" and not args.allow_pending:
        print(f"::error::{date} is a HELD draft, not a published post. Read "
              f"state/panel/{date}-{slot}.md first, then either promote it "
              "(site-publish workflow) or rerun with --allow-pending.")
        return 1

    already = LG.flagged(date, name)
    if already and not args.force:
        if args.live:
            print(f"::error::the ledger says the {slot} for {date} already went "
                  "to Facebook. Refusing a second post. Use --force only if "
                  "you have checked the Page and it is not there.")
            return 1
        print(f"note: the {slot} for {date} is already on Facebook; --live "
              "would refuse without --force.")

    if args.live and not args.allow_stale:
        why = staleness(date, slot, now)
        if why:
            print(f"::error::refusing a live post: {why} Rerun with "
                  "--allow-stale if this is really what you want.")
            return 1

    print("=" * 66)
    print(body)
    print("=" * 66)

    if not args.live:
        print("DRY RUN -- nothing posted. Rerun with --live to post this to "
              "the Page.")
        return 0

    try:
        result = post(body, force_live=True)
    except Exception as exc:  # noqa: BLE001
        print(f"::error::Facebook post failed: {exc}")
        print("The day is NOT flagged; this can be retried.")
        return 1
    post_id = (result or {}).get("id")
    if not post_id:
        print(f"::error::Facebook returned no post id ({result!r}). The day is "
              "NOT flagged; check the Page before retrying.")
        return 1
    LG.flag(date, name)
    print(f"posted to the Page: {post_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
