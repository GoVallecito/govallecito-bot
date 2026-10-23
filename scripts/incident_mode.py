"""
Incident mode: pause the upbeat conditions card while the county has an emergency.

WHY (2026-10-23). During the Oct 22-23 Vallecito flood the owner had to flip the
CONDITIONS_BOT_ENABLED repo variable off by hand so a cheerful afternoon card would
not land between evacuation posts. This does that automatically. The variable still
works as an override: "false" keeps the bot off no matter what this says.

WHAT COUNTS AS AN INCIDENT, read from govallecito.com/data/lpc-alerts.json (the same
feed scripts/site_alerts.py posts from):
  * any active county entry with kind "alert" and level "danger";
  * any active county entry with kind "clear" received in the last CLEAR_COOLDOWN
    (an all-clear is not the moment for "beautiful day at the lake");
  * any stream chip with level "danger".
conditions.json is not read: the stream chips above already carry the gauge danger
levels, and one fetch is one less way for this to be slow.

FAILS OPEN. If the feed cannot be fetched or parsed, the card posts as normal. An
upbeat post must never block on the site, and this is not a safety path: the
emergency path (check_emergency.py) fails closed on its own.
"""

import time
from datetime import timedelta

import site_alerts

CLEAR_COOLDOWN = timedelta(hours=2)


def incident_reason(feed, now_ms=None):
    """A one-line reason the upbeat post should wait, or None. Pure; no network."""
    if not isinstance(feed, dict):
        return None
    now_ms = now_ms if now_ms is not None else time.time() * 1000
    cooldown_ms = CLEAR_COOLDOWN.total_seconds() * 1000
    for a in feed.get("active") or []:
        if not isinstance(a, dict):
            continue
        expires = a.get("expiresMs")
        if isinstance(expires, (int, float)) and expires <= now_ms:
            continue
        label = (a.get("subject") or a.get("id") or "county entry").strip()
        if a.get("kind") == "alert" and a.get("level") == "danger":
            return f"active county danger alert: {label}"
        received = a.get("receivedMs")
        if a.get("kind") == "clear" and isinstance(received, (int, float)) and now_ms - received < cooldown_ms:
            return f"county all-clear less than {int(CLEAR_COOLDOWN.total_seconds() // 3600)} h ago: {label}"
    for chip in feed.get("stream") or []:
        if isinstance(chip, dict) and chip.get("level") == "danger":
            return f"stream gauge at danger: {chip.get('text') or chip.get('id')}"
    return None


def check(get_json, now_ms=None):
    """Fetch the site feed and return incident_reason(), or None when the fetch fails
    (fail open). get_json: fetch_conditions._get_json-compatible callable."""
    try:
        feed = get_json(site_alerts.SITE_ALERTS_URL)
    except Exception as exc:  # noqa: BLE001 -- never let the site block a routine post
        print(f"[incident_mode] could not fetch {site_alerts.SITE_ALERTS_URL} ({exc}); posting normally.")
        return None
    return incident_reason(feed, now_ms)
