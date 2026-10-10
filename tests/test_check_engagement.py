"""
The engagement feedback loop: classify every Graph failure, never fail silently.

Background: from 2026-07-26 to 2026-10-10 every engagement read failed with
Graph error #10 because the Page token lacked pages_read_user_content. The
workflow stayed green, each failure was retried for 14 days and then written
off, and content_preferences.json never received a single data point. The
error payloads below are the ones the live API returned to the read-only
probe (run 38084760366), trimmed.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import check_engagement as CE  # noqa: E402
import post_history  # noqa: E402

TOKEN = "SECRET-TEST-TOKEN-must-never-print"

ERR_NEEDS_USER_CONTENT = {"error": {
    "message": "(#10) This endpoint requires the 'pages_read_user_content' permission or the "
               "'Page Public Content Access' feature.",
    "type": "OAuthException", "code": 10}}
ERR_OBJECT_GONE = {"error": {
    "message": "(#10) Object does not exist, cannot be loaded due to missing permission or "
               "reviewable feature, or does not support this operation.",
    "type": "OAuthException", "code": 10}}
ERR_TOKEN_DEAD = {"error": {"message": "Error validating access token", "type": "OAuthException",
                            "code": 190}}
ERR_SERVER = {"error": {"message": "An unexpected error has occurred.", "type": "OAuthException",
                        "code": 2}}
OK_ENGAGEMENT = {"id": "x",
                 "reactions": {"data": [], "summary": {"total_count": 4}},
                 "comments": {"data": [], "summary": {"total_count": 2, "order": "ranked"}},
                 "shares": {"count": 1}}


class Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class FakeGraph:
    """Answers by (post_id, which-read). which-read is "engagement" for the
    fields read and "id" for the follow-up bare id read."""

    def __init__(self, table):
        self.table = table
        self.calls = []

    def __call__(self, url, params=None, headers=None, timeout=None):
        post_id = url.rsplit("/", 1)[-1]
        which = "id" if params.get("fields") == "id" else "engagement"
        self.calls.append((post_id, which, params, headers))
        answer = self.table[(post_id, which)]
        if isinstance(answer, Exception):
            raise answer
        return Resp(*answer)


def ago(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def post(pid, hours_old=72, **extra):
    rec = {"post_id": pid, "posted_at": ago(hours_old), "slot": "morning",
           "hook_line": "Morning check-in from the lake.", "had_image": True,
           "post_type": "daily", "engagement_checked": False, "engagement": None}
    rec.update(extra)
    return rec


@pytest.fixture
def history(tmp_path, monkeypatch):
    path = tmp_path / "post_history.json"
    monkeypatch.setattr(post_history, "HISTORY_PATH", str(path))
    monkeypatch.setattr(CE, "PREFERENCES_PATH", str(tmp_path / "content_preferences.json"))

    def write(posts):
        path.write_text(json.dumps({"posts": posts}))

    def read():
        return {p["post_id"]: p for p in json.loads(path.read_text())["posts"]}

    return write, read


def test_requests_counts_only_with_reactions_not_likes(history):
    write, read = history
    write([post("p1")])
    fake = FakeGraph({("p1", "engagement"): (200, OK_ENGAGEMENT)})
    stats = CE.update_pending_engagement(TOKEN, get=fake)

    fields = fake.calls[0][2]["fields"]
    assert "reactions.summary(total_count).limit(0)" in fields
    assert "comments.summary(true).limit(0)" in fields
    assert "likes" not in fields
    assert "access_token" not in fake.calls[0][2]  # token rides in the header, never the URL
    assert fake.calls[0][3]["Authorization"] == f"Bearer {TOKEN}"

    rec = read()["p1"]
    assert rec["engagement"] == {"reactions": 4, "comments": 2, "shares": 1, "total": 7}
    assert rec["engagement_checked"] is True and rec["engagement_unavailable"] is False
    assert stats["ok"] == 1 and not stats["loop_broken"]


def test_missing_shares_key_is_zero_not_an_error(history):
    write, read = history
    write([post("p1")])
    body = {k: v for k, v in OK_ENGAGEMENT.items() if k != "shares"}
    CE.update_pending_engagement(TOKEN, get=FakeGraph({("p1", "engagement"): (200, body)}))
    assert read()["p1"]["engagement"]["shares"] == 0


def test_permission_error_stops_the_run_and_touches_no_post(history):
    """The 2026 bug: the post is readable, its reactions are not."""
    write, read = history
    write([post("p1"), post("p2"), post("p3")])
    fake = FakeGraph({
        ("p1", "engagement"): (400, ERR_NEEDS_USER_CONTENT),
        ("p1", "id"): (200, {"id": "p1"}),
    })
    stats = CE.update_pending_engagement(TOKEN, get=fake)

    assert stats["permission"] == 1 and stats["loop_broken"]
    assert "pages_read_user_content" in stats["permission_error"]
    assert [c[0] for c in fake.calls] == ["p1", "p1"]  # stopped; p2 and p3 never called
    recs = read()
    assert all(r["engagement_checked"] is False for r in recs.values())
    assert all("engagement_attempts" not in r for r in recs.values())


def test_permission_error_never_writes_a_post_off_even_when_old(history):
    write, read = history
    write([post("old", hours_old=24 * 60)])
    CE.update_pending_engagement(TOKEN, get=FakeGraph({
        ("old", "engagement"): (400, ERR_NEEDS_USER_CONTENT),
        ("old", "id"): (200, {"id": "old"}),
    }))
    assert read()["old"]["engagement_checked"] is False


def test_dead_token_is_a_permission_error(history):
    write, _ = history
    write([post("p1")])
    stats = CE.update_pending_engagement(TOKEN, get=FakeGraph({
        ("p1", "engagement"): (400, ERR_TOKEN_DEAD),
        ("p1", "id"): (400, ERR_TOKEN_DEAD),
    }))
    assert stats["permission"] == 1 and stats["loop_broken"]


def test_deleted_post_is_recorded_once_and_not_retried(history):
    """What the probe saw for the 2026-07-24 post: even its id is unreadable."""
    write, read = history
    write([post("gone"), post("p2")])
    fake = FakeGraph({
        ("gone", "engagement"): (400, ERR_OBJECT_GONE),
        ("gone", "id"): (400, ERR_OBJECT_GONE),
        ("p2", "engagement"): (200, OK_ENGAGEMENT),
    })
    stats = CE.update_pending_engagement(TOKEN, get=fake)
    rec = read()["gone"]
    assert rec["engagement_unavailable"] is True
    assert rec["engagement_unavailable_reason"] == "post_unreadable"
    assert stats["gone"] == 1 and stats["ok"] == 1 and not stats["loop_broken"]

    fake.calls.clear()
    CE.update_pending_engagement(TOKEN, get=fake)
    assert fake.calls == []  # neither post is due again


def test_legacy_writeoffs_are_reopened_but_new_ones_are_not(history):
    """The 69 posts written off before the fix carry no reason; they get one
    more look. Anything written off by the new code carries a reason."""
    write, read = history
    legacy = dict(engagement_checked=True, engagement=None, engagement_unavailable=True,
                  engagement_checked_at=ago(24 * 50))
    write([
        post("legacy", hours_old=24 * 70, **legacy),
        post("tagged", hours_old=24 * 70, **legacy, engagement_unavailable_reason="post_unreadable"),
        post("done", engagement_checked=True, engagement={"total": 3}),
    ])
    fake = FakeGraph({("legacy", "engagement"): (200, OK_ENGAGEMENT)})
    CE.update_pending_engagement(TOKEN, get=fake)
    assert [c[0] for c in fake.calls] == ["legacy"]
    rec = read()["legacy"]
    assert rec["engagement"]["total"] == 7 and rec["engagement_unavailable"] is False


def test_reopened_old_post_gets_three_tries_before_giving_up_again(history):
    write, read = history
    write([post("legacy", hours_old=24 * 70, engagement_checked=True, engagement=None,
                engagement_unavailable=True)])
    fake = FakeGraph({("legacy", "engagement"): (500, ERR_SERVER)})
    for attempt in (1, 2):
        CE.update_pending_engagement(TOKEN, get=fake)
        rec = read()["legacy"]
        assert rec["engagement_attempts"] == attempt
        assert not rec.get("engagement_unavailable_reason")
    CE.update_pending_engagement(TOKEN, get=fake)
    assert read()["legacy"]["engagement_unavailable_reason"] == "gave_up_transient"


def test_young_post_is_never_given_up_on_attempt_count_alone(history):
    write, read = history
    write([post("p1", hours_old=72, engagement_attempts=9)])
    CE.update_pending_engagement(TOKEN, get=FakeGraph({("p1", "engagement"): (500, ERR_SERVER)}))
    assert read()["p1"]["engagement_checked"] is False


def test_network_failure_is_transient_and_never_prints_the_token(history, capsys):
    write, _ = history
    write([post("p1")])
    boom = ConnectionError(f"https://graph.facebook.com/v25.0/p1?access_token={TOKEN}")
    stats = CE.update_pending_engagement(TOKEN, get=FakeGraph({("p1", "engagement"): boom}))
    assert stats["transient"] == 1
    assert TOKEN not in capsys.readouterr().out


def test_one_blip_is_not_a_broken_loop_but_two_with_nothing_read_is(history):
    write, _ = history
    write([post("p1")])
    fail = (500, ERR_SERVER)
    assert not CE.update_pending_engagement(TOKEN, get=FakeGraph({("p1", "engagement"): fail}))["loop_broken"]

    write([post("p1"), post("p2")])
    stats = CE.update_pending_engagement(TOKEN, get=FakeGraph({
        ("p1", "engagement"): fail, ("p2", "engagement"): fail}))
    assert stats["loop_broken"]


def test_nothing_due_is_not_broken(history):
    write, _ = history
    write([post("fresh", hours_old=2)])
    stats = CE.update_pending_engagement(TOKEN, get=FakeGraph({}))
    assert stats["attempted"] == 0 and not stats["loop_broken"]


def test_main_exits_2_on_permission_error(history, monkeypatch):
    write, _ = history
    write([post("p1")])
    fake = FakeGraph({
        ("p1", "engagement"): (400, ERR_NEEDS_USER_CONTENT),
        ("p1", "id"): (200, {"id": "p1"}),
    })
    monkeypatch.setattr(CE.requests, "get", fake)
    monkeypatch.setenv("FB_PAGE_ACCESS_TOKEN", TOKEN)
    assert CE.main() == CE.EXIT_LOOP_BROKEN


def test_main_exits_0_when_reads_work(history, monkeypatch):
    write, _ = history
    write([post("p1")])
    monkeypatch.setattr(CE.requests, "get", FakeGraph({("p1", "engagement"): (200, OK_ENGAGEMENT)}))
    monkeypatch.setenv("FB_PAGE_ACCESS_TOKEN", TOKEN)
    assert CE.main() == 0


def test_preferences_report_what_was_collected_and_drop_impressions(history):
    write, _ = history
    write([
        post("a", engagement_checked=True, engagement={"reactions": 3, "comments": 1, "shares": 0, "total": 4}),
        post("b", had_image=False, engagement_checked=True,
             engagement={"reactions": 0, "comments": 0, "shares": 0, "total": 0}),
        post("alert", post_type="emergency_alert", engagement_checked=True,
             engagement={"reactions": 50, "comments": 9, "shares": 9, "total": 68}),
        post("gone", engagement_checked=True, engagement=None, engagement_unavailable=True,
             engagement_unavailable_reason="post_unreadable"),
    ])
    prefs = CE.compute_preferences()
    assert "impressions" not in prefs
    assert prefs["collected"] == {"checked_count": 2,
                                  "totals": {"reactions": 3, "comments": 1, "shares": 0}}
    assert prefs["sample_counts"]["grounded_vs_plain"] == {"grounded": 1, "plain": 1}
    assert prefs["hook_weights"] == {"morning": {}, "afternoon": {}}  # far below MIN_SAMPLES
