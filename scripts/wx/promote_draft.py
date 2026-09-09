#!/usr/bin/env python3
"""
Promote a staged forecast to the live site feed.

    python scripts/wx/promote_draft.py 2026-09-08
    python scripts/wx/promote_draft.py --list

This is the approval step the review loop never had. Guardrails could hold a
post and notify a human, and the human could read it, and then there was
nothing to do about it except switch the whole gate off. Now: read the issue,
run this with the date, and that exact post, the one you read, goes live on the
website. Nothing is recomposed and nothing else changes.

Deliberately separate from the Facebook path. The site can start publishing
while the Facebook page stays dark, which is the right order, because the site
has no audience to disappoint and every page compounds into search.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wx import site as SITE  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("date", nargs="?", help="date (2026-09-08) or full slug")
    ap.add_argument("--list", action="store_true", help="show staged posts")
    ap.add_argument("--site-dir", default=None)
    args = ap.parse_args()

    if args.list or not args.date:
        pending = SITE.list_pending(args.site_dir)
        if not pending:
            print(f"Nothing staged in {SITE.pending_dir(args.site_dir)}")
            return 0
        print(f"Staged in {SITE.pending_dir(args.site_dir)}:")
        for name in pending:
            print(f"  {name}")
        print("\nPromote one with: python scripts/wx/promote_draft.py <date>")
        return 0

    try:
        result = SITE.promote(args.date, args.site_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"promoted -> {result['post']}")
    print(f"feed      -> {result['feed']}")
    print("\nCommit and push, or run the 'Publish approved forecast' workflow, "
          "and the site will pick it up on its next build.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
