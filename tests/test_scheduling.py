"""
The scheduling regression suite.

WHAT THIS IS FOR. The first live week produced three school calls in eight
days, and every run exited zero the whole time. Nothing crashed; the posts
simply did not happen, and the design made that indistinguishable from a quiet
morning. Two independent causes:

  1. The clock check required the local hour to equal 5 exactly. GitHub's
     hourly cron actually delivered 4 to 7 runs a day at arbitrary minutes, so
     the 5 o'clock hour was never sampled on half the days.
  2. On the one day a run DID land at 05:46, two Open-Meteo bands returned 429,
     http.get_json refused to retry any 4xx, the dead-man switch fired and the
     day was lost with no retry.

Every test below pins one of those two, plus the invariants that make the fix
safe: no duplicate posts inside a wide window, and a loud signal when a day
still ends up empty.
"""
import datetime
import os
import sys
import tempfile
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))

from wx import constants as C          # noqa: E402
from wx import ledger as LG            # noqa: E402
from wx import run_forecast as RF      # noqa: E402
from wx.sources import http as H       # noqa: E402

TZ = C._TZ if hasattr(C, "_TZ") else None


def _at(hour, minute=0, day=8):
    from zoneinfo import ZoneInfo
    return datetime.datetime(2026, 9, day, hour, minute,
                             tzinfo=ZoneInfo(C.TIMEZONE))


class _TempState:
    """Point the ledger at a scratch dir so tests never touch real state."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp()
        self.prev = os.environ.get("WX_STATE_DIR")
        os.environ["WX_STATE_DIR"] = self.dir
        return self

    def __exit__(self, *a):
        if self.prev is None:
            os.environ.pop("WX_STATE_DIR", None)
        else:
            os.environ["WX_STATE_DIR"] = self.prev


# --- the window ------------------------------------------------------------

def test_the_whole_morning_window_posts_not_just_five_oclock():
    """THE REGRESSION. 05:46 and 07:01 both have to work.

    Real delivered run times from the failed week: 04:55, 08:00, 05:46, 07:01.
    Under the old exact-hour rule only 05:46 produced anything.
    """
    with _TempState():
        for hour, minute in [(5, 0), (5, 46), (6, 30), (7, 1), (8, 59)]:
            assert RF.determine_slot(now=_at(hour, minute)) == "school_call", \
                f"{hour:02d}:{minute:02d} should post and did not"


def test_outside_the_window_still_exits():
    with _TempState():
        for hour in (0, 4, 9, 10, 12, 17, 23):
            assert RF.determine_slot(now=_at(hour)) is None, f"hour {hour}"


def test_window_covers_school_decision_deadline():
    """A call that lands after the districts decide is a different product.

    The window must open before 06:30 and it must not run so late that the post
    is written to a parent whose kid is already at school.
    """
    lo, hi = C.SCHOOL_CALL_WINDOW
    assert lo <= 5, "window must open at or before the 5am target"
    assert hi <= 10, "a school call at 10am is not a school call"


# --- idempotency -----------------------------------------------------------

def test_second_run_in_the_window_does_not_post_again():
    """A four hour window means several runs land inside it. One may post."""
    with _TempState():
        assert RF.determine_slot(now=_at(5, 10)) == "school_call"
        LG.record("2026-09-08", "school_call", note="pass")
        assert RF.determine_slot(now=_at(6, 40)) is None
        assert RF.determine_slot(now=_at(8, 5)) is None


def test_an_aborted_run_leaves_the_day_open():
    """The 2026-09-04 case. A data abort must not consume the morning.

    The ledger entry is written after a draft exists, never before, so a run
    that dies on the dead-man switch is followed by a retry.
    """
    with _TempState():
        assert RF.determine_slot(now=_at(5, 46)) == "school_call"
        # run aborts, records nothing
        assert RF.determine_slot(now=_at(7, 30)) == "school_call"


def test_the_ledger_keys_on_the_date_the_post_is_for():
    """An evening run writes tomorrow's post and must key it to tomorrow."""
    assert RF._target_date(_at(5, 46)) == "2026-09-08"
    assert RF._target_date(_at(19, 30)) == "2026-09-09"


def test_yesterdays_entry_does_not_block_today():
    with _TempState():
        LG.record("2026-09-07", "school_call")
        assert RF.determine_slot(now=_at(5, 46, day=8)) == "school_call"


# --- the miss alarm --------------------------------------------------------

def test_a_missed_morning_reports_itself_exactly_once():
    """Silence was the failure mode. It has to become a signal."""
    with _TempState():
        seen = []

        class FakeNotify:
            @staticmethod
            def miss_reported(slot, date_iso, streak=None):
                seen.append((slot, date_iso, tuple(streak or ())))

        real = RF.N
        RF.N = FakeNotify
        try:
            RF.determine_slot(now=_at(11, 5))   # window closed, nothing posted
            RF.determine_slot(now=_at(14, 5))   # later run same day
            RF.determine_slot(now=_at(20, 5))
        finally:
            RF.N = real
        assert len(seen) == 1, f"expected one report, got {seen}"
        assert seen[0][0] == "school_call"
        assert seen[0][1] == "2026-09-08"


def test_a_morning_that_posted_reports_no_miss():
    with _TempState():
        LG.record("2026-09-08", "school_call", note="pass")
        seen = []

        class FakeNotify:
            @staticmethod
            def miss_reported(*a, **k):
                seen.append(a)

        real = RF.N
        RF.N = FakeNotify
        try:
            RF.determine_slot(now=_at(11, 5))
        finally:
            RF.N = real
        assert seen == []


def test_no_miss_report_before_the_window_has_closed():
    """A 2am run must not report a morning that has not happened yet."""
    with _TempState():
        seen = []

        class FakeNotify:
            @staticmethod
            def miss_reported(*a, **k):
                seen.append(a)

        real = RF.N
        RF.N = FakeNotify
        try:
            RF.determine_slot(now=_at(2, 5))
        finally:
            RF.N = real
        assert seen == []


# --- the 429 that lost 2026-09-04 ------------------------------------------

def _http_error(code):
    return urllib.error.HTTPError("http://x", code, "boom", {}, None)


def test_429_is_retried():
    """429 means 'not now'. It used to be treated as 'the request is wrong'."""
    calls = {"n": 0}

    def flaky(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(429)

        class R:
            def read(self):
                return b'{"ok": true}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R()

    real = H.urllib.request.urlopen
    H.urllib.request.urlopen = flaky
    try:
        assert H.get_json("http://example.invalid") == {"ok": True}
    finally:
        H.urllib.request.urlopen = real
    assert calls["n"] == 3, "should have retried twice before succeeding"


def test_404_is_still_not_retried():
    """The original rule was right about this: a 404 is a real answer."""
    calls = {"n": 0}

    def always404(req, timeout=None):
        calls["n"] += 1
        raise _http_error(404)

    real = H.urllib.request.urlopen
    H.urllib.request.urlopen = always404
    try:
        try:
            H.get_json("http://example.invalid")
            assert False, "should have raised"
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
    finally:
        H.urllib.request.urlopen = real
    assert calls["n"] == 1, "a 404 must not be retried"


def test_retryable_set_is_exactly_the_two_transient_codes():
    assert H.RETRYABLE_4XX == {408, 429}


# --- day type --------------------------------------------------------------

def test_sunday_is_not_a_school_day():
    """2026-09-06 shipped a 'school call' on a Sunday."""
    assert C.day_type(datetime.date(2026, 9, 6)) == "weekend"
    assert C.day_type(datetime.date(2026, 9, 8)) == "school day"
    assert C.day_type(datetime.date(2026, 7, 8)) == "summer break"


# --- the content regressions the week actually produced --------------------

def test_present_tense_pass_conditions_are_blocked():
    """The 2026-09-02 draft shipped this and the guardrail did not see it.

    'The passes are dry, Coal Bank, Molas, Red Mountain and Wolf Creek all
    clear.' is a road surface report with no CDOT data behind it.
    """
    from wx import guardrails as G
    from test_guardrails import GOOD_BUNDLE
    text = ("09/02/26 5:44am: Morning, its Wednesday. The passes are dry, Coal "
            "Bank, Molas, Red Mountain and Wolf Creek all clear.")
    verdict, reasons = G.evaluate(GOOD_BUNDLE, text, first_30_days=False)
    assert verdict == G.BLOCK, f"expected BLOCK, got {verdict}: {reasons}"
    assert any("road surface" in r for r in reasons), reasons


def test_forecasting_the_passes_still_passes():
    """The guardrail must not block the thing passes.py exists to do."""
    from wx import guardrails as G
    from test_guardrails import GOOD_BUNDLE
    text = ("09/02/26 5:44am: Morning, its Wednesday. Coal Bank and Molas "
            "should stay dry through the morning, and any ice up top would be "
            "early before the sun gets it. Check CDOT for status.")
    verdict, why = G.evaluate(GOOD_BUNDLE, text, first_30_days=False)
    assert verdict != G.BLOCK, why


def test_the_brief_shows_the_model_its_own_recent_openers():
    """Three drafts in a row opened 'Morning, its <day>.' and closed the same.

    The model cannot avoid repeating a shape it cannot see.
    """
    from wx import compose as CO
    bundle = {
        "post_for_weekday": "Tuesday", "post_for_date": "2026-09-08",
        "post_for_stamp": "09/08/26", "generated_at": "2026-09-08T05:46:00",
        "season": "fall", "day_type": "school day", "is_late": False,
        "recent_posts": [
            {"date": "2026-09-06", "opened": "Morning, its Sunday.",
             "closed": "What are you seeing at your place this morning?"},
        ],
        "alerts": [], "bands": {}, "missing": [],
    }
    brief = CO.render_bundle(bundle, post_type="school_call")
    assert "Morning, its Sunday." in brief
    assert "Do not reuse any of these shapes" in brief


def test_a_weekend_brief_drops_the_school_frame():
    from wx import compose as CO
    bundle = {
        "post_for_weekday": "Sunday", "post_for_date": "2026-09-06",
        "post_for_stamp": "09/06/26", "generated_at": "2026-09-06T05:21:00",
        "season": "fall", "day_type": "weekend", "is_late": False,
        "recent_posts": [], "alerts": [], "bands": {}, "missing": [],
    }
    brief = CO.render_bundle(bundle, post_type="school_call")
    assert "There is no school run to write about" in brief


def test_a_late_run_is_told_it_is_late():
    from wx import compose as CO
    bundle = {
        "post_for_weekday": "Tuesday", "post_for_date": "2026-09-08",
        "post_for_stamp": "09/08/26", "generated_at": "2026-09-08T07:40:00",
        "season": "fall", "day_type": "school day", "is_late": True,
        "composed_hour": 7, "recent_posts": [], "alerts": [], "bands": {},
        "missing": [],
    }
    brief = CO.render_bundle(bundle, post_type="school_call")
    assert "RUNNING LATE" in brief


def test_the_system_prompt_contains_no_dash_it_forbids():
    """The prompt banned em dashes in a document full of them.

    Models imitate the style of their context, so a rule demonstrated in the
    breach is a rule half enforced. sanitize.py catches the output either way;
    this stops the model fighting its own instructions.
    """
    from wx import compose as CO
    prompt = CO.load_system_prompt()
    assert "—" not in prompt, "em dash in the prompt that forbids em dashes"
    assert "–" not in prompt, "en dash in the prompt that forbids en dashes"


def test_the_prompt_still_carries_the_load_bearing_rules():
    """A rewrite must not quietly drop a rule that took a week to learn."""
    from wx import compose as CO
    p = CO.load_system_prompt().lower()
    for needle in ["fluh-ree-duh", "never claim a degree", "percent of median",
                   "exactly one", "el nino", "lake-effect", "6:30",
                   "urgency raises precision"]:
        assert needle in p, f"the prompt lost: {needle}"


# --- state isolation -------------------------------------------------------

def test_no_module_derives_a_state_path_from_its_own_location():
    """A regression guard, not a unit test.

    verify.py resolved the forecast log and the snow line CALIBRATION from
    __file__, so every run outside a workflow, this suite included, wrote into
    the live repo state. The calibration file is the learned offset behind the
    signature number of the whole product; a fixture landing in it is a silent
    corruption of every future snow line.

    Any state path must be cwd-relative and must honour WX_STATE_DIR.
    """
    import pathlib
    import re
    root = pathlib.Path(__file__).parent.parent / "scripts" / "wx"
    offenders = []
    pattern = re.compile(r"(STATE_DIR|_LOG|CALIBRATION|state\")\s*=\s*os\.path\.join\("
                         r"[^)]*(REPO_ROOT|__file__)")
    for path in root.rglob("*.py"):
        src = path.read_text()
        for m in pattern.finditer(src):
            offenders.append(f"{path.name}: {m.group(0)[:70]}")
    assert not offenders, "state paths derived from __file__: " + "; ".join(offenders)


def test_verify_writes_into_wx_state_dir():
    import json
    from wx import verify as V
    with _TempState() as t:
        V.FORECAST_LOG = None
        V.CALIBRATION = None
        bundle = {"post_for_date": "2026-09-08", "local_date": "2026-09-08",
                  "generated_at": "2026-09-08T05:46:00-06:00",
                  "snow_line": {"representative_ft": 8200}}
        V.record_forecast(bundle, {"vallecito": [2, 5]}, post_id=None)
        written = os.path.join(t.dir, "forecast_log.json")
        assert os.path.exists(written), os.listdir(t.dir)
        assert json.load(open(written))["forecasts"]
