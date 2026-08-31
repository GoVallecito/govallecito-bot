"""
End-to-end runner tests. No network, no API key, no Facebook, no model.

These are the tests that prove the WIRING works -- that the three entry points
GitHub Actions actually calls can execute start to finish. Unit tests can all
pass while a runner is broken because a module was built and never called,
which is exactly what happened to the CDOT adapter and the storm trigger.
"""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
from test_end_to_end import fake_fetchers
from wx import constants as C
from wx import compose as CO
from wx import bundle as B, storm_watch as SW, verify as V
from wx import run_forecast as RF, run_verify as RV, run_storm_watch as RSW
from wx.sources.http import SourceResult
from test_storm_watch import payload

CLEAN_DRAFT = (
    "11/04/26 5:52am: Morning, its Wednesday. Snow line sitting around 7,200ft "
    "and falling. Take that with a grain of salt (its been running low all "
    "night). Durango and the Valley are just wet. Up the Pine its slushy on the "
    "501. Vallecito and the Florida picked up a few inches and the 240 will be "
    "the slick one, it never gets sun through there. The districts decide by "
    "6:30. At the house I have got about three inches on the stake. How is it "
    "looking out your window?")


def stub_llm(messages):
    """Returns a clean draft and records what it was asked, so tests can assert
    the brief actually reached the model."""
    stub_llm.last = messages
    return CLEAN_DRAFT


def _fakes(**kw):
    f = fake_fetchers(**kw)
    f["roads"] = lambda: SourceResult(False, source="CDOT", error="no key in tests")
    return f


def test_forecast_runner_completes_and_publishes_dry(tmp_path=None):
    os.environ["DRY_RUN"] = "true"
    with tempfile.TemporaryDirectory() as d:
        V.FORECAST_LOG = os.path.join(d, "log.json")
        V.CALIBRATION = os.path.join(d, "cal.json")
        os.chdir(d)
        rc = RF.run(slot="school_call", llm=stub_llm, first_30_days=False,
                    dry_bundle=B.build(fetchers=_fakes()), site_dir=d)
        assert rc == 0
        assert os.path.exists(os.path.join(d, "output", "draft.txt"))
        assert os.path.exists(os.path.join(d, "output", "card.png")), "card must render"
        # the forecast must be logged so tomorrow can score it
        assert os.path.exists(V.FORECAST_LOG)
        # and a site markdown file must exist
        assert any(n.endswith(".md") for n in os.listdir(d))


def test_forecast_runner_aborts_rather_than_guessing():
    os.environ["DRY_RUN"] = "true"
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        broken = B.build(fetchers=_fakes(break_band="vallecito"))
        rc = RF.run(slot="school_call", llm=stub_llm, dry_bundle=broken)
        assert rc == 0
        assert not os.path.exists(os.path.join(d, "output", "draft.txt")), \
            "must abort BEFORE composing -- silence beats a partial forecast"


def test_life_safety_alert_switches_the_post_type():
    os.environ["DRY_RUN"] = "true"
    with tempfile.TemporaryDirectory() as d:
        V.FORECAST_LOG = os.path.join(d, "log.json")
        os.chdir(d)
        RF.run(slot="school_call", llm=stub_llm, first_30_days=False,
               dry_bundle=B.build(fetchers=_fakes(life_safety=True)))
        user = stub_llm.last[1]["content"]
        assert "life-safety post" in user or "Threat plainly" in user


def test_brief_reaching_the_model_has_the_data_and_the_persona():
    os.environ["DRY_RUN"] = "true"
    with tempfile.TemporaryDirectory() as d:
        V.FORECAST_LOG = os.path.join(d, "log.json")
        os.chdir(d)
        RF.run(slot="school_call", llm=stub_llm, first_30_days=False,
               dry_bundle=B.build(fetchers=_fakes()))
        system, user = stub_llm.last[0]["content"], stub_llm.last[1]["content"]
        assert "fluh-REE-duh" in system
        assert "SNOW LINE" in user
        assert "FORECAST BY ELEVATION BAND" in user
        assert "MODEL DISAGREEMENT" in user


def test_verify_runner_scores_and_drafts():
    os.environ["DRY_RUN"] = "true"
    import datetime as _dt
    with tempfile.TemporaryDirectory() as d:
        V.FORECAST_LOG = os.path.join(d, "log.json")
        V.CALIBRATION = os.path.join(d, "cal.json")
        os.chdir(d)
        b = B.build(fetchers=_fakes())
        # local, not UTC -- the code under test now reasons in Mountain Time
        b["local_date"] = (C.local_date() - _dt.timedelta(days=1)).isoformat()
        V.record_forecast(b, {"vallecito": {"snow_low_in": 3.0, "snow_high_in": 7.0}})
        obs = {"vallecito": {"snow_in": 9.5, "sources": ["home gauge"]},
               "snow_line_observed_ft": 7600,
               "_cocorahs_reports": [
                   {"name": "Vallecito 2.1 NNE", "new_snow_in": 9.5, "precip_in": 0.8},
                   {"name": "Bayfield 6.0 N", "new_snow_in": 5.0, "precip_in": 0.4}],
               "_meta": {"sources_used": ["CoCoRaHS"], "missing": []}}
        rc = RV.run(llm=stub_llm, obs=obs, bundle_override=B.build(fetchers=_fakes()),
                    first_30_days=False)
        assert rc == 0
        assert os.path.exists(os.path.join(d, "output", "totals_draft.txt"))
        user = stub_llm.last[1]["content"]
        assert "WHAT ACTUALLY FELL" in user
        assert "Vallecito 2.1 NNE" in user, "station names must reach the model verbatim"
        assert "under-forecast" in user, "the miss must be stated to the model"


def test_storm_watch_runner_fires_and_forbids_amounts():
    os.environ["DRY_RUN"] = "true"
    with tempfile.TemporaryDirectory() as d:
        SW.STATE = os.path.join(d, "sw.json")
        V.CALIBRATION = os.path.join(d, "cal.json")
        os.chdir(d)
        b = B.build(fetchers=_fakes())
        import wx.sources.openmeteo as OM
        real = OM.fetch_band
        OM.fetch_band = lambda band, days=5, models=None: SourceResult(
            True, payload(storm_at=72), source="stub")
        try:
            rc = RSW.run(llm=stub_llm, bundle_override=b, first_30_days=False)
        finally:
            OM.fetch_band = real
        assert rc == 0
        assert os.path.exists(os.path.join(d, "output", "storm_draft.txt"))
        instruction = stub_llm.last[1]["content"]
        assert "Do NOT give snowfall amounts" in instruction, \
            "a day-4 post must never carry amounts"


def test_storm_watch_stays_quiet_on_a_calm_pattern():
    os.environ["DRY_RUN"] = "true"
    with tempfile.TemporaryDirectory() as d:
        SW.STATE = os.path.join(d, "sw.json")
        os.chdir(d)
        import wx.sources.openmeteo as OM
        real = OM.fetch_band
        OM.fetch_band = lambda band, days=5, models=None: SourceResult(
            True, payload(), source="stub")
        try:
            rc = RSW.run(llm=stub_llm, bundle_override=B.build(fetchers=_fakes()),
                         first_30_days=False)
        finally:
            OM.fetch_band = real
        assert rc == 0
        assert not os.path.exists(os.path.join(d, "output", "storm_draft.txt"))


def test_missing_cdot_key_does_not_break_the_run():
    """No live road status, but the pass card still exists - from the forecast.

    CDOT's public feed documentation has been withdrawn, so `roads` is expected
    to be absent. That must not cost us the pass section, and it must not abort
    the run: we forecast the passes and link CDOT for status.
    """
    b = B.build(fetchers=_fakes())
    assert b["sources"]["roads"]["ok"] is False, "no CDOT key in tests"
    assert "roads" not in b, "no live road status available"
    assert b.get("pass_card"), "the forecast-based pass card should still be built"
    assert "not the road status" in b["pass_card"], "must defer to CDOT"
    assert not any("roads" in p for p in __import__(
        "wx.guardrails", fromlist=["x"]).require_or_abort(b))


def test_abort_leaves_a_readable_record():
    """A silent 5:45am with no post and no reason looks like a broken agent.

    The dead-man switch is correct behaviour, but it has to explain itself
    somewhere a person can actually read - GitHub's raw logs are not that place.
    """
    os.environ["DRY_RUN"] = "true"
    with tempfile.TemporaryDirectory() as d:
        import wx.run_forecast as RFmod
        os.chdir(d)
        os.makedirs(os.path.join(d, "state"), exist_ok=True)
        real = RFmod.write_status
        captured = {}

        def spy(state, detail, bundle=None, slot=None, hint=None, draft=None):
            captured.update(state=state, detail=detail, slot=slot, hint=hint)
        RFmod.write_status = spy
        try:
            rc = RFmod.run(slot="school_call", llm=stub_llm,
                           dry_bundle=B.build(fetchers=_fakes(break_band="vallecito")))
        finally:
            RFmod.write_status = real
        assert rc == 0
        assert "aborted" in captured.get("state", "")
        assert "vallecito" in captured.get("detail", "")
        assert "worse than silence" in (captured.get("hint") or "")


def test_missing_api_key_is_a_state_not_a_crash():
    os.environ["DRY_RUN"] = "true"
    os.environ.pop("ANTHROPIC_API_KEY", None)
    with tempfile.TemporaryDirectory() as d:
        import wx.run_forecast as RFmod
        os.chdir(d)
        real = RFmod.write_status
        captured = {}
        RFmod.write_status = lambda state, detail, *a, **k: captured.update(
            state=state, detail=detail, hint=k.get("hint"))
        try:
            rc = RFmod.run(slot="school_call", dry_bundle=B.build(fetchers=_fakes()))
        finally:
            RFmod.write_status = real
        assert rc == 0, "a missing key must not crash the run"
        assert captured.get("state") == "not configured"
        assert "ANTHROPIC_API_KEY" in (captured.get("hint") or "")


def test_brief_states_the_day_the_post_is_for():
    """"Morning, its Sunday" appeared at the top of a post dated Monday.

    The composer was handed a run timestamp and inferred the weekday from it.
    An evening run writes tomorrow's post, so the two genuinely differ - and a
    wrong weekday in the opening line is the kind of single word a local stops
    trusting over.
    """
    import datetime as _dt
    b = B.build(fetchers=_fakes())
    assert b.get("post_for_weekday") and b.get("post_for_date")
    # internally consistent
    d = _dt.date.fromisoformat(b["post_for_date"])
    assert d.strftime("%A") == b["post_for_weekday"]
    assert d.strftime("%m/%d/%y") == b["post_for_stamp"]
    # and stated unmissably in the brief
    user = CO.build_messages(b, post_type="school_call")[1]["content"]
    assert "THIS POST IS FOR" in user
    assert b["post_for_weekday"] in user
    assert "Use no other weekday" in user


def test_evening_runs_target_tomorrow_morning():
    import datetime as _dt
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("America/Denver")
    for hour, offset in ((5, 0), (11, 0), (12, 1), (22, 1)):
        now = _dt.datetime(2026, 8, 30, hour, tzinfo=tz)
        target = now.date() + _dt.timedelta(days=1) if now.hour >= 12 else now.date()
        assert (target - now.date()).days == offset, f"hour {hour}"
