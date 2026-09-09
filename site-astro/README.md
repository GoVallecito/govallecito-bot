# Weather pages for govallecito.com

Six files. Copy them into the site repo, deploy, done. No token, no secret, no
new dependency, and nothing to configure in this repo.

```
src/lib/wx.ts                        reads the feed at build time
src/pages/weather/index.astro        today's forecast
src/pages/weather/[slug].astro       one page per forecast  <- the SEO work
src/pages/weather/_WxPost.astro      shared renderer
src/pages/weather/archive.astro      every forecast, by month
src/pages/weather/record.astro       the public track record
src/pages/weather/rss.xml.ts         feed for aggregators
```

## How it works, and why it is built this way

The forecaster lives in `GoVallecito/govallecito-bot`. This site lives
somewhere else. Getting a post from one to the other has two obvious shapes and
both cost something:

**Push into the site repo.** The forecast workflow checks out this repository
and commits into it. That needs a personal access token with write access to a
second repo, stored as a secret in the first. It is the largest new credential
surface this project would have, and that exact token has already been created
and revoked once.

**Pull from the bot repo.** No token, because the bot repo is public. But the
naive version walks the GitHub contents API and makes one request per post,
against a 60-per-hour unauthenticated limit shared by every build runner on
that IP. It works in testing and fails under load, which is the worst way for
something to fail.

This takes the second shape and removes its cost. The forecaster writes each
post into its own repo, which its workflow already commits, and rewrites a
single `feed.json` holding the full text of every recent forecast. This site
makes **one** unauthenticated request per build and has everything.

No credential exists anywhere in that path.

## Install

1. Copy the six files in, keeping the paths above.
2. If the site has a layout component, replace the `<html>`/`<head>`/`<body>`
   scaffolding in the four page files with it. Everything inside `<main>` is
   the part that matters; the scaffolding is only there so these build
   standalone.
3. Make sure `astro.config.mjs` sets `site: 'https://govallecito.com'` so
   canonical URLs and the RSS feed resolve.
4. Deploy. `/weather/` renders the latest forecast, and every forecast gets its
   own dated URL.

There is nothing to add to `src/content/config.ts`. This deliberately does not
use a content collection, so there is no schema to merge with yours and no
chance of breaking an existing collection.

## Rebuilding when a new forecast lands

A static site does not know the feed changed. Create a build hook and give it
to the bot repo:

- **Netlify:** Site settings, Build hooks, Add build hook. Copy the URL.
- **Cloudflare Pages:** Settings, Builds, Deploy hooks. Copy the URL.

Then in `GoVallecito/govallecito-bot`: Settings, Secrets and variables,
Actions, New repository secret, named `SITE_DEPLOY_HOOK`, pasted URL.

That is the only secret in the whole path, and a build hook can start a build
and do nothing else. If it is never set, nothing breaks; the site just picks up
new forecasts whenever it next builds.

## If the feed cannot be reached

The build still succeeds. `getFeed()` never throws: it logs a warning, returns
an empty feed, and the weather pages render an honest empty state while every
other page on the site builds exactly as before. This is tested by killing the
feed and building, and it matters, because govallecito.com is a business and
the weather section is a feature of it.

## Why the byline says Up the Pine Weather

A tourism brand has a structural incentive to say come. A forecaster sometimes
has to say the pass is bad and the ramps are out. Same site, separate byline,
like a columnist, so neither job quietly erodes the other.

## Verified

Built against Astro 7.3.2 with a real feed: six routes generated, dated pages,
canonical URLs, JSON-LD, RSS. Then built again with the feed unreachable: exit
0, empty state, no other page affected.
