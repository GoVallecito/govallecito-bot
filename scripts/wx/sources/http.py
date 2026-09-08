"""
One HTTP helper for every source adapter, with the project's failure contract
baked in.

THE CONTRACT, inherited from the existing bot's fetch_conditions.py and
extended: a source that is unreachable, slow, or returns something
unrecognized returns None. It never raises, and it never returns a partial
structure that looks complete. The composer's job is then to say "data
delayed" -- or, for the forecaster, to post NOTHING AT ALL.

That last part is the difference between this and the conditions bot. A
conditions card with a missing lake level is still a useful post. A forecast
built on half its inputs is worse than silence, because people make travel and
school decisions on it at 5:45am. See guardrails.require_or_abort().
"""

import json
import time
import urllib.error
import urllib.request

from .. import constants as C


# 429 Too Many Requests and 408 Request Timeout are 4xx codes that mean "not
# now," not "not ever." Everything else in the 4xx range is a real answer.
RETRYABLE_4XX = {408, 429}

# A ceiling on Retry-After. A source telling us to come back in an hour is
# telling us it is down for this run; the forecaster has minutes, not hours.
MAX_RETRY_AFTER = 8


def _sleep_for_retry_after(exc):
    """Honour a Retry-After header when the server sends a usable one."""
    try:
        raw = exc.headers.get("Retry-After") if exc.headers else None
        wait = min(float(raw), MAX_RETRY_AFTER) if raw else 0
    except (TypeError, ValueError):
        wait = 0
    if wait > 0:
        print(f"[http] {exc.code}, Retry-After {wait}s")
        time.sleep(wait)


class SourceResult:
    """Wraps a fetch so provenance travels with the data.

    Every number that reaches a post can answer three questions: where did you
    come from, when were you measured, and are you stale. The composer is
    instructed never to state a number without a source, and this is what makes
    that enforceable rather than aspirational.
    """

    __slots__ = ("ok", "data", "source", "url", "fetched_at", "error", "age_note")

    def __init__(self, ok, data=None, source=None, url=None, error=None, age_note=None):
        self.ok = ok
        self.data = data
        self.source = source
        self.url = url
        self.error = error
        self.age_note = age_note
        self.fetched_at = time.time()

    def to_dict(self):
        return {
            "ok": self.ok,
            "data": self.data,
            "source": self.source,
            "url": self.url,
            "error": self.error,
            "age_note": self.age_note,
        }

    def __repr__(self):
        return f"<SourceResult {self.source} ok={self.ok} err={self.error!r}>"


def get_json(url, headers=None, timeout=None, retries=2, backoff=1.5):
    """GET a URL and parse JSON. Returns the parsed object, or raises.

    Callers should be adapter functions that catch and convert to SourceResult;
    this deliberately raises so the adapter decides what a failure means for
    its own field.

    Retries are for transient failures only. A 404 means the station id is
    wrong and retrying it three times just makes the run slower before it fails
    the same way.

    BUT: 429 and 408 are 4xx codes that are NOT "the request is wrong." 429 is
    "you asked too fast," and Open-Meteo returns it when the four elevation
    bands and the four model-spread calls go out back to back. On 2026-09-04
    the 05:46 run reached the posting hour, took a 429 on two of the four
    bands, refused to retry them because the old rule was a flat
    `400 <= code < 500`, tripped the dead-man switch and lost the day. Those
    two codes are now retried, with Retry-After honoured when the server sends
    it.
    """
    hdrs = {"User-Agent": C.USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    timeout = timeout or C.REQUEST_TIMEOUT

    last_exc = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            return json.loads(raw.decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            # 4xx is a real answer: the request is wrong. Don't retry it,
            # EXCEPT for the two codes that mean "not now" rather than "no".
            if 400 <= exc.code < 500 and exc.code not in RETRYABLE_4XX:
                raise
            last_exc = exc
            _sleep_for_retry_after(exc)
        except Exception as exc:  # noqa: BLE001 -- adapters convert this
            last_exc = exc
        if attempt < retries:
            time.sleep(backoff ** attempt)
    raise last_exc


def get_text(url, headers=None, timeout=None, retries=2):
    hdrs = {"User-Agent": C.USER_AGENT}
    if headers:
        hdrs.update(headers)
    timeout = timeout or C.REQUEST_TIMEOUT
    last_exc = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code not in RETRYABLE_4XX:
                raise
            last_exc = exc
            _sleep_for_retry_after(exc)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
        if attempt < retries:
            time.sleep(1.5 ** attempt)
    raise last_exc
