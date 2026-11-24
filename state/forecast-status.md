# Forecast run: aborted, data unavailable

When: 2026-11-24T05:04:54-07:00 (Mountain)
Slot: `school_call`
heldDays: 7

> **STANDING FAILURE: 7 consecutive days held, nothing published.** This is a pipeline problem, not a run of bad drafts. Check the panel transcripts in `state/panel/` for the same objection repeating, and `site/weather/_pending/` for what is stacking up.

## Detail

```
no forecast for durango
no forecast for bayfield
no forecast for vallecito
```

**What to do:** No post went out, deliberately. A forecast built on half its inputs is worse than silence at 5:45am. If this repeats, check state/selftest-latest.md for which source is down.

## What the data looked like

- Snow line: no precipitation forecast
- Alerts: none
- Missing sources: ['band:durango', 'band:bayfield', 'band:vallecito']
- Pass forecast: built

