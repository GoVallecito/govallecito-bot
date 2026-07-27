# GoVallecito Daily Conditions Post — Template & Style Guide

Purpose: give every "lake conditions" post the same bones — same order, same icons, same sign-off — so that six months from now a post looks like it belongs to the same brand as the first one, even though the numbers inside it change every time.

## Voice

Practical, direct, a little dry. No hype, no exclamation-point stacking, no "amazing lake day ahead!!" energy. This mirrors the site's own tone ("Know the lake before you go," "Loved hard and kept pristine") — informational first, personality second. Emoji are used as *functional icons* (the same way the site's nav uses 🛏️🎣🌡️), not decoration. If a data feed is stale or delayed — the site itself sometimes labels things "delayed" — the post says so rather than presenting old numbers as fresh. That honesty is part of the brand, not a flaw to hide.

**Updated 2026-07-27:** every post now also carries a real visual (most of the time — see "Visual" below) and closes with a genuine, specific call-to-action question. Neither of those requires abandoning the voice above. A CTA is one plain, specific question ("what did the water look like at your spot today?"), not a hype line with an exclamation point — the research behind this change (current Facebook engagement practice, checked this same session rather than assumed) says specific beats generic, not that dry has to become loud. If a future edit to the CTA copy ever starts reading like a marketing email, that's a bug against this section, not an acceptable side effect of "better CTAs."

## Fixed structure — same order, every single post

1. **Date + one-line hook** (the only line that's allowed to rotate/have personality) — as of 2026-07-27 every hook is also tagged with a topic (lake / weather-forecast / fishing / hiking / sunset / stargazing — see `generate_post_text.py`'s `HOOK_TOPICS`), which drives both the visual (below) and the closing CTA.
2. 💧 **Lake level** — % of full pool + elevation
3. 🌡️ **Weather** — current temp, then AM/PM/evening in one line
4. 🔥 **Fire status** — restriction stage + what's actually restricted, stated plainly
5. 🌊 **Streamflow** — if the feed has it; omit the line entirely if not, don't fake it
6. *(optional, only when noteworthy)* one situational line — air quality, road closure, wildlife, a lake event, a fishing-report or site-section spotlight (see "Grounded content" below)
7. **Closing CTA** — one genuine, specific question tied to the hook's topic (added 2026-07-27; see "Visual + CTA" below). Not optional, not generic filler.
8. **Sign-off** — link to full conditions + fixed hashtag set

## Visual + CTA (added 2026-07-27)

Every routine post (not the emergency-alert variant — see below) now attempts a real, safely-licensed photo tied to the hook's topic, rendered as the card's photo band, plus a closing CTA question in the caption for that same topic. Config lives in `config/evergreen_topics.json`; code in `generate_post_text.py`'s `_try_evergreen_topic_image()` / `_topic_cta()`.

**"Attempts," not "guarantees."** The photo search only accepts public-domain/CC0 Wikimedia Commons images (same license gate the seasonal-almanac photos already used, unchanged) — that gate does not get relaxed just to force an image onto every post. In practice this means most posts get a real photo and a small fraction don't, depending on what Commons currently has available in the on-topic categories. A text-only post is a fine, intentional fallback, not a failure — the alternative (loosening the license filter, or using a photo that isn't genuinely of this place) was considered and rejected as a worse tradeoff than an occasional missing photo.

**The photo is a real photo of the Vallecito Reservoir / Weminuche Wilderness / San Juan National Forest area. It is not necessarily a photo taken today or tonight.** The sunset and stargazing topics in particular are mood/seasonal framing paired with a real place photo — the copy is written to avoid claiming otherwise (e.g. "catch the evening light at the lake tonight?" rather than "here's tonight's sunset").

**Emergency alerts are excluded on purpose.** `build_alert_post()` does not get a topic photo or a CTA question — a "tell us in the comments" line under a fire or evacuation alert would be tone-deaf, and a scenic photo would compete with the alert for attention. Safety posts stay exactly as lean as they were before this change.

## Icon key (fixed mapping — never swap an icon between categories)

| Icon | Always means |
|---|---|
| 💧 | Lake level |
| 🌡️ | Weather / temperature |
| 🔥 | Fire danger / restrictions |
| 🌊 | Streamflow |
| 🌫️ | Air quality |
| 🛣️ | Road conditions |
| 🌙 | Sun & moon |

## Hashtags (fixed core, every post)

`#VallecitoLake #KnowBeforeYouGo #SanJuanMountains` — plus optionally one time-of-day tag (`#MorningReport` / `#AfternoonUpdate`) so the two daily slots are visually distinguishable at a glance.

## What's allowed to vary day to day

- The actual numbers (obviously)
- The opening hook line — rotate through a small bank of openers so it doesn't feel copy-pasted, but never change what comes after it
- The hook's topic (lake / weather-forecast / fishing / hiking / sunset / stargazing), and with it, which photo category gets tried and which CTA question closes the post
- Whether a photo actually appears — depends on what's available under an open license that run (see "Visual + CTA" above); never depends on relaxing the license rule
- The optional situational line (section 6) — most days this is just omitted
- A "did you know" / seasonal-color line, or a fishing-report / site-section spotlight, at most once or twice a week, never replacing the core data

## What never varies

- Section order
- Icon-to-category mapping
- The core hashtag set
- Sign-off format and link
- The closing CTA being a genuine, specific question — never a generic "like and share!" line
- The photo license rule (public domain / CC0 only) — never relaxed to guarantee an image appears
- Emergency alerts never get a topic photo or CTA — safety content only, unchanged since before 2026-07-27

---

## Example posts

These use the numbers govallecito.com was displaying on Jul 22, 2026 — several were flagged "delayed" on the site itself, so treat the figures below as illustrative of the *format*, not as verified live conditions.

### Morning slot example

> **Wednesday, July 22 — good morning, Vallecito.**
>
> 💧 Lake: 53% of full pool (elev. 7,642 ft, full pool is 7,665 ft)
> 🌡️ 74°F now, headed to a high of 81° — clear and calm for anyone heading out early
> 🔥 Stage 2 fire restrictions in effect: no campfires or charcoal, anywhere. Two active wildfires within 50 miles — nothing threatening the lake right now.
> 🌊 Streamflow: data delayed, check back this afternoon
>
> Full conditions → govallecito.com
> #VallecitoLake #KnowBeforeYouGo #SanJuanMountains #MorningReport

### Afternoon slot example

> **Wednesday afternoon at the lake.**
>
> 💧 Lake holding at 53% of full pool
> 🌡️ 81°F, clear skies — evening's looking calm, upper 50s by nightfall
> 🔥 Stage 2 restrictions still in effect: no campfires or charcoal
> 🌫️ Air quality: 34 AQI (good) at the lake, Moderate regionally
>
> Full conditions → govallecito.com
> #VallecitoLake #KnowBeforeYouGo #SanJuanMountains #AfternoonUpdate

### Afternoon slot example, with a photo + CTA (added 2026-07-27)

> *[card renders with a real Vallecito-area photo as its photo band, headline "Golden hour's coming up at the dam."]*
>
> **Wednesday afternoon at the lake — golden hour's coming up at the dam.**
>
> 💧 Lake: 53% of full pool (elev. 7,642 ft)
> 🌡️ 81°F, clear skies — upper 50s by nightfall
> 🔥 Stage 2 restrictions still in effect: no campfires or charcoal
> 🌊 Streamflow: 92 cfs combined inflow
>
> Catch the evening light at the lake tonight? Share what you saw in the comments.
>
> Full conditions → govallecito.com
> #VallecitoLake #KnowBeforeYouGo #SanJuanMountains #AfternoonUpdate

This is the same fixed row order as every other example on this page, plus the photo band and the closing CTA question — nothing about the core data structure changed to make room for either.

### Safety-priority variant (use whenever restrictions change or a wildfire is newly detected)

**This variant is implemented and automated** as of the emergency-alert
system (`scripts/check_emergency.py`, `scripts/generate_post_text.py`'s
`build_alert_post()`) — and generalized beyond fire to flood, evacuation,
and disaster alerts too, each with its own headline/hashtag/emoji but the
same underlying shape: the alert leads, brief lake/weather context follows,
no seasonal photo. See the README's "Emergency alerts" section for exactly
how it's triggered and its real limitations. The fire-specific example below
is kept as the original illustration of the pattern.

> **Fire status update — Vallecito.**
>
> 🔥 Stage 2 fire restrictions remain in effect as of July 20: no campfires or charcoal anywhere in the area.
> 🚨 2 wildfires currently detected within 50 miles (source: NIFC / InciWeb) — not threatening the lake as of this post.
> 💧 Lake: 53% of full pool
> 🌡️ 74°F, high of 81°
>
> Always check current status before any open flame → govallecito.com
> #VallecitoLake #KnowBeforeYouGo #FireSafety

---

## Notes for whoever (or whatever) writes these

- Never guess a number. If the feed is down, say "data delayed" the way the site itself does — don't carry yesterday's number forward silently.
- Keep the data rows to 4-6 lines of actual content. This is a scan-and-go utility post, not an essay — the hook, closing CTA, and sign-off are structurally separate from that budget, not exempt from having one of their own (see the char-budget constants in `generate_post_text.py`).
- The fire/safety section outranks everything else in importance even though it's listed 4th structurally — if restrictions change, that's what leads the situational line or gets its own post (see the safety-priority variant).
- Adding a new evergreen topic (beyond lake / weather-forecast / fishing / hiking / sunset / stargazing) means checking its Commons categories actually exist and contain real, on-topic, usably-licensed photos first — the same discipline `seasonal_almanac.json` and `site_spotlights.json` already require. Don't add a category to `config/evergreen_topics.json` because the name sounds plausible; check it on Commons directly, the way this file's own initial category list was checked.
- The CTA question for a topic should be answerable by an actual visitor from an actual comment — "what's biting," "which trail," "what did you see" — not a rhetorical or rate-my-post question ("isn't this lake beautiful?"). If a CTA can't realistically get a specific, real reply, rewrite it.
