# Weather pages for govallecito.com

Seven files. Copy them into the site repo keeping their paths, deploy, done.
No token, no secret, no new dependency.

```
src/lib/wx.ts                        reads the feed, renders a post
src/pages/weather/index.astro        today's forecast
src/pages/weather/[slug].astro       one page per forecast  <- the SEO work
src/pages/weather/archive.astro      every forecast, by month
src/pages/weather/record.astro       the public track record
src/pages/weather/rss.xml.ts         feed for aggregators
functions/weather/index.ts           serves /weather live  <- see below
```

## How a forecast gets here

The forecaster lives in `GoVallecito/govallecito-bot`. This site lives
somewhere else. Getting a post across has two obvious shapes and both cost
something:

**Push into the site repo.** Needs a token with write access to a second
repository, stored as a secret in the first. Largest new credential surface
this project would have, and that exact token has already been revoked once.

**Pull from the bot repo.** No token, because the bot repo is public. But the
naive version walks the GitHub contents API once per post, against a
60-per-hour unauthenticated limit shared by every build runner on that IP. It
works in testing and fails under load.

This takes the second shape and removes its cost. The forecaster writes each
post into its own repo, which its workflow already commits, and rewrites a
single `feed.json` holding the full text of every recent forecast. This site
makes **one** unauthenticated request per build. No credential exists anywhere
in that path.

## Why there is a Pages Function

`govallecito-web` is a **direct-upload** Pages project, not a Git-connected
one. Cloudflare only offers deploy hooks on Git-connected projects, so there is
no hook to fire when a forecast lands. The site redeploys itself every few
hours through its own rebake, which is fine for the archive but not for the one
page whose entire value is being current at 6am.

So `/weather` does not wait for a rebuild. `functions/weather/index.ts`:

1. asks for the statically built page with `context.next()`
2. fetches the feed, edge-cached for two minutes
3. swaps the newest forecast into `<div id="wx-live">` with HTMLRewriter, and
   updates `<title>` and the meta description to match

It starts from the **built page** rather than rendering its own HTML, so the
site's header, nav, footer, styles and analytics come through untouched and
this file never has to know anything about them. It replaces the contents of
one element and leaves every other byte alone.

`<div id="wx-live">` in `index.astro` is load-bearing. Rename or remove that id
and the function silently stops updating, leaving the built page in place: a
graceful failure, but a stale one.

Only `/weather` is affected. The dated pages, archive, record and RSS are
static and are not touched by the function.

## Install

1. Copy the seven files in, keeping the paths above.
2. If the site has a layout component, replace the `<html>`/`<head>`/`<body>`
   scaffolding in the four page files with it. Everything inside `<main>` is
   the part that matters; the scaffolding is only there so these build
   standalone. **Keep `<div id="wx-live">` wherever the forecast ends up.**
3. Make sure `astro.config.mjs` sets `site: 'https://govallecito.com'`.
4. Deploy.

There is nothing to add to `src/content/config.ts`. This deliberately does not
use a content collection, so there is no schema to merge and no existing
collection to break.

## If the feed cannot be reached

Nothing breaks, at either layer.

**At build time** `getFeed()` never throws: it logs a warning, returns an empty
feed, and the weather pages render an empty state while every other page on the
site builds exactly as before.

**At request time** the function returns the built page **byte for byte
identical** to what Astro produced. There is no path through it that produces
an error page.

That matters because govallecito.com is a business and the weather section is a
feature of it.

## One renderer

`postToHtml()` in `src/lib/wx.ts` is used by the Astro build *and* by the Pages
Function. They render the same post in two places at two different times, and
if each had its own template they would drift, which a reader would see as the
page changing shape when it went live.

## Why the byline says Up the Pine Weather

A tourism brand has a structural incentive to say come. A forecaster sometimes
has to say the pass is bad and the ramps are out. Same site, separate byline,
like a columnist, so neither job quietly erodes the other.

## Verified, not assumed

Built against **Astro 7.3.2** with a real feed: six routes generated, dated
pages, canonical URLs, JSON-LD, RSS. Then rebuilt with the feed unreachable:
exit 0, empty state, no other page affected.

The function was run under **wrangler 4.130.0** (`wrangler pages dev`) against
that same build output:

- feed up: `data-wx-source="live"`, fresh title, `x-wx-forecast-for` header set,
  site furniture intact
- feed down: response **byte-identical** to `dist/weather/index.html`
- marker missing: page passed through untouched, and the title deliberately
  *not* rewritten, so the page can never advertise a forecast it does not show
- `/weather/archive/`, `/weather/record/`, `/weather/rss.xml` and the dated
  pages all still 200 and unmodified

Two bugs came out of actually running it rather than reading it. A bare
`YYYY-MM-DD` parses as UTC midnight and rendered as the *previous day* in
Mountain Time. And a handler class with a private field named `text` failed at
runtime with "Incorrect type for the 'text' field on 'ElementContentHandlers'",
because HTMLRewriter looks for `element`, `text`, `comments` and `end` on the
handler and the field shadowed the callback it expects.
