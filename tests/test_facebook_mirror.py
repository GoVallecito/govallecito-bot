"""The narrow Facebook path: one published forecast, mirrored byte for byte.

WHY. vars.DRY_RUN gates five posting paths at once, so it cannot be flipped to
put the morning forecast on Facebook without restarting the other four. The
fix is a per-call override (publish.post_to_page(force_live=True)) with two
callers only: the human-run mirror in wx/post_to_fb.py, and the
WX_FB_AUTO_SLOTS allowlist in run_forecast. These tests pin that the override
stays narrow, that the mirror never rewrites what it posts, and that it cannot
post twice or post the wrong day.

No network: every Graph call is a fake. Every pre-staleness --live test passes
--allow-stale so the suite does not depend on the wall clock.
"""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pytest  # noqa: E402

from wx import ledger as LG          # noqa: E402
from wx import post_to_fb as PF      # noqa: E402
from wx import publish as P          # noqa: E402
from wx import run_forecast as RF    # noqa: E402
from wx import site as SITE          # noqa: E402

TZ = ZoneInfo("America/Denver")
DATE = "2026-09-28"
MORNING = datetime(2026, 9, 28, 6, 0, tzinfo=TZ)
BODY = ("09/28/26 5:45am: Morning, its Monday.\n\nRain up the Florida by noon, "
        "and the 501 should see wet pavement by the afternoon.\n\n"
        "How's it looking at your place?")


def bundle(for_date=DATE):
    """The real shape, as in tests/test_site.py."""
    return {
        "post_for_date": for_date,
        "local_date": for_date,
        "generated_at": f"{for_date}T05:05:38-06:00",
        "snow_line": {},
        "alerts": [],
        "precip_type_by_band": {
            "vallecito": {"elevation_ft": 7650, "precip_type": "rain",
                          "label": "Vallecito and the Florida"}},
        "sources": {"a": {"source": "Open-Meteo"}, "b": {"source": "NWS GJT"}},
        "basin": {"pct_of_median": 64},
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    site = tmp_path / "site"
    monkeypatch.setenv("WX_SITE_DIR", str(site))
    monkeypatch.setenv("WX_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("WX_FB_AUTO_SLOTS", raising=False)
    monkeypatch.chdir(tmp_path)
    return site


class Poster:
    def __init__(self, reply=None, boom=None):
        self.calls, self.reply, self.boom = [], reply, boom

    def __call__(self, text, **kw):
        self.calls.append((text, kw))
        if self.boom:
            raise self.boom
        return {"id": "1138532512682553_42"} if self.reply is None else self.reply


def _run(*args, post=None, now=MORNING):
    return PF.main(list(args), now=now, post=post or Poster())


# --- finding the post ------------------------------------------------------------

def test_the_body_comes_back_byte_identical(env):
    SITE.publish(BODY, bundle(), "school_call", out_dir=str(env))
    path, body, where = PF.find_post(DATE)
    assert where == "published"
    assert body == BODY
    post = Poster()
    assert _run("--date", DATE, "--live", "--allow-stale", post=post) == 0
    assert post.calls[0][0] == BODY, "the page must get the site's text, untouched"


def test_a_pending_draft_is_found_and_labelled(env):
    SITE.stage(BODY, bundle(), "school_call", out_dir=str(env))
    path, body, where = PF.find_post(DATE)
    assert where == "pending" and "_pending" in path and body == BODY


def test_published_beats_a_stale_pending_copy(env):
    SITE.stage("an older held draft " * 8, bundle(), "school_call", out_dir=str(env))
    SITE.publish(BODY, bundle(), "school_call", out_dir=str(env))
    path, body, where = PF.find_post(DATE)
    assert where == "published" and body == BODY


def test_a_missing_date_finds_nothing_and_posts_nothing(env):
    SITE.publish(BODY, bundle(), "school_call", out_dir=str(env))
    assert PF.find_post("2026-09-01") is None
    post = Poster()
    assert _run("--date", "2026-09-01", "--live", "--allow-stale", post=post) == 1
    assert post.calls == []


# --- posting ---------------------------------------------------------------------

def test_without_live_nothing_posts_even_when_dry_run_is_false(env, monkeypatch, capsys):
    monkeypatch.setenv("DRY_RUN", "false")
    SITE.publish(BODY, bundle(), "school_call", out_dir=str(env))
    post = Poster()
    assert _run("--date", DATE, post=post) == 0
    assert post.calls == []
    out = capsys.readouterr().out
    assert "DRY RUN -- nothing posted" in out and BODY in out
    assert not LG.flagged(DATE, "fb:school_call")


def test_a_live_run_forces_past_dry_run_and_flags_the_ledger(env):
    SITE.publish(BODY, bundle(), "school_call", out_dir=str(env))
    post = Poster()
    assert _run("--date", DATE, "--live", "--allow-stale", post=post) == 0
    assert post.calls == [(BODY, {"force_live": True})]
    assert LG.flagged(DATE, "fb:school_call")


def test_the_flag_stops_a_second_post_and_force_gets_past_it(env):
    SITE.publish(BODY, bundle(), "school_call", out_dir=str(env))
    post = Poster()
    assert _run("--date", DATE, "--live", "--allow-stale", post=post) == 0
    assert _run("--date", DATE, "--live", "--allow-stale", post=post) == 1
    assert len(post.calls) == 1, "the same forecast reached the page twice"
    assert _run("--date", DATE, "--live", "--allow-stale", "--force", post=post) == 0
    assert len(post.calls) == 2


def test_a_failed_graph_call_leaves_the_day_unflagged(env):
    SITE.publish(BODY, bundle(), "school_call", out_dir=str(env))
    post = Poster(boom=RuntimeError("Facebook page post failed: timed out"))
    assert _run("--date", DATE, "--live", "--allow-stale", post=post) == 1
    assert not LG.flagged(DATE, "fb:school_call"), "a retry must still be possible"


def test_a_reply_with_no_post_id_is_a_failure_and_stays_unflagged(env):
    SITE.publish(BODY, bundle(), "school_call", out_dir=str(env))
    post = Poster(reply={"success": True})
    assert _run("--date", DATE, "--live", "--allow-stale", post=post) == 1
    assert not LG.flagged(DATE, "fb:school_call")


def test_a_held_draft_is_refused_without_allow_pending(env, capsys):
    SITE.stage(BODY, bundle(), "school_call", out_dir=str(env))
    post = Poster()
    assert _run("--date", DATE, "--live", "--allow-stale", post=post) == 1
    assert post.calls == []
    assert f"state/panel/{DATE}-school_call.md" in capsys.readouterr().out
    assert _run("--date", DATE, "--live", "--allow-stale", "--allow-pending",
                post=post) == 0
    assert len(post.calls) == 1


# --- the override stays narrow ---------------------------------------------------

def test_dry_run_still_governs_a_call_that_does_not_force(env, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "")      # an unconfigured Actions variable
    sent = []
    monkeypatch.setattr(P, "_graph_post", lambda *a: sent.append(a) or {"id": "x"})
    out = P.post_to_page(BODY, token="t")
    assert out.get("dry_run") is True and sent == []


def test_force_live_bypasses_dry_run_and_hits_feed(env, monkeypatch, capsys):
    monkeypatch.setenv("DRY_RUN", "true")
    sent = []
    monkeypatch.setattr(P, "_graph_post",
                        lambda path, fields: sent.append((path, fields)) or {"id": "1_2"})
    out = P.post_to_page(BODY, page_id="123", token="t", force_live=True)
    assert out == {"id": "1_2"}
    assert sent[0][0] == "123/feed" and sent[0][1]["message"] == BODY
    assert "force_live=True" in capsys.readouterr().out, "an override is never silent"


def test_fb_auto_slots_parsing(monkeypatch):
    monkeypatch.delenv("WX_FB_AUTO_SLOTS", raising=False)
    assert RF._fb_auto_slots() == set()
    monkeypatch.setenv("WX_FB_AUTO_SLOTS", "")
    assert RF._fb_auto_slots() == set()
    monkeypatch.setenv("WX_FB_AUTO_SLOTS", " school_call , evening,, ")
    assert RF._fb_auto_slots() == {"school_call", "evening"}


# --- the automatic path in run_forecast ------------------------------------------

class FakeLedger:
    def __init__(self):
        self.flags = set()

    def flagged(self, date, name):
        return (date, name) in self.flags

    def flag(self, date, name):
        self.flags.add((date, name))


def _auto(env, monkeypatch, allow, post):
    monkeypatch.setenv("WX_FB_AUTO_SLOTS", allow)
    lg = FakeLedger()
    monkeypatch.setattr(RF, "_ledger", lambda *a, **k: lg)
    monkeypatch.setattr(RF.P, "post_to_page", post)
    paths = SITE.publish(BODY, bundle(), "school_call", out_dir=str(env))
    RF._mirror_to_facebook(paths["post"], bundle(), "school_call")
    return lg


def test_auto_path_does_nothing_for_a_slot_not_allowlisted(env, monkeypatch, capsys):
    post = Poster()
    lg = _auto(env, monkeypatch, "evening", post)
    assert post.calls == [] and lg.flags == set()
    assert "not in WX_FB_AUTO_SLOTS" in capsys.readouterr().out


def test_auto_path_posts_the_file_on_disk_and_flags(env, monkeypatch):
    post = Poster()
    lg = _auto(env, monkeypatch, "school_call", post)
    assert post.calls == [(BODY, {"force_live": True})]
    assert (DATE, "fb:school_call") in lg.flags


def test_auto_path_failure_is_a_warning_not_a_crash(env, monkeypatch, capsys):
    post = Poster(boom=RuntimeError("Facebook error: token expired"))
    lg = _auto(env, monkeypatch, "school_call", post)   # must not raise
    assert lg.flags == set()
    out = capsys.readouterr().out
    assert "::warning::" in out and "facebook-post workflow" in out


# --- staleness -------------------------------------------------------------------

def test_a_live_post_of_a_stale_date_is_refused(env):
    SITE.publish(BODY, bundle("2026-09-27"), "school_call", out_dir=str(env))
    post = Poster()
    assert _run("--date", "2026-09-27", "--live", post=post) == 1
    assert post.calls == []


def test_a_dry_run_of_any_date_at_any_hour_still_works(env, capsys):
    SITE.publish(BODY, bundle("2026-09-27"), "school_call", out_dir=str(env))
    late = datetime(2026, 9, 28, 22, 30, tzinfo=TZ)
    assert _run("--date", "2026-09-27", now=late) == 0
    assert "DRY RUN -- nothing posted" in capsys.readouterr().out


@pytest.mark.parametrize("date,slot,now,stale", [
    (DATE, "school_call", MORNING, False),
    ("2026-09-27", "school_call", MORNING, True),     # a mistyped date
    (DATE, "school_call", datetime(2026, 9, 28, 11, 0, tzinfo=TZ), True),
    # An evening look written at 22:00 is FOR the next day, like the bundle says.
    ("2026-09-29", "evening", datetime(2026, 9, 28, 22, 0, tzinfo=TZ), False),
])
def test_staleness(date, slot, now, stale):
    assert (PF.staleness(date, slot, now) is not None) is stale
