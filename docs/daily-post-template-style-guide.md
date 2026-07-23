# GoVallecito Daily Conditions Post — Template & Style Guide

Purpose: give every "lake conditions" post the same bones — same order, same icons, same sign-off — so that six months from now a post looks like it belongs to the same brand as the first one, even though the numbers inside it change every time.

## Voice

Practical, direct, a little dry. No hype, no exclamation-point stacking, no "amazing lake day ahead!!" energy. This mirrors the site's own tone ("Know the lake before you go," "Loved hard and kept pristine") — informational first, personality second. Emoji are used as *functional icons* (the same way the site's nav uses 🛏️🎣🌡️), not decoration. If a data feed is stale or delayed — the site itself sometimes labels things "delayed" — the post says so rather than presenting old numbers as fresh. That honesty is part of the brand, not a flaw to hide.

## Fixed structure — same order, every single post

1. **Date + one-line hook** (the only line that's allowed to rotate/have personality)
2. 💧 **Lake level** — % of full pool + elevation
3. 🌡️ **Weather** — current temp, then AM/PM/evening in one line
4. 🔥 **Fire status** — restriction stage + what's actually restricted, stated plainly
5. 🌊 **Streamflow** — if the feed has it; omit the line entirely if not, don't fake it
6. *(optional, only when noteworthy)* one situational line — air quality, road closure, wildlife, a lake event
7. **Sign-off** — link to full conditions + fixed hashtag set

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
- The optional situational line (section 6) — most days this is just omitted
- A "did you know" / seasonal-color line, at most once or twice a week, never replacing the core data

## What never varies

- Section order
- Icon-to-category mapping
- The core hashtag set
- Sign-off format and link

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
- Keep it to 4-6 lines of actual content. This is a scan-and-go utility post, not an essay.
- The fire/safety section outranks everything else in importance even though it's listed 4th structurally — if restrictions change, that's what leads the situational line or gets its own post (see the safety-priority variant).
