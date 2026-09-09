"""
The site publishing path, and the self-correction that keeps a morning alive.

CONTEXT. For the first week the site integration did not exist. The code wrote
a markdown file into WX_SITE_DIR, which resolves inside the bot's own Actions
checkout, and that checkout is deleted when the job ends. Setting the variable
published into a container that was then thrown away.

The fix publishes into this repo's own tree, which the workflow already
commits, so the public site can read it with no credential at all. These tests
pin the contract the site build depends on: one feed file, one request, every
post in it, newest first, and nothing staged for review leaking into it.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))

from wx import guardrails as G   # noqa: E402
from wx import site as SITE      # noqa: E402


def bundle(for_date="2026-09-08", snow=None):
    return {
        "post_for_date": for_date,
        "local_date": for_date,
        "generated_at": f"{for_date}T05:05:38-06:00",
        "snow_line": {"representative_ft": snow, "trend": "falling"} if snow else {},
        "alerts": [],
        "precip_type_by_band": {
            "vallecito": {"elevation_ft": 7650, "precip_type": "rain",
                          "label": "Vallecito and the Florida"}},
        "sources": {"a": {"source": "Open-Meteo"}, "b": {"source": "NWS GJT"}},
        "basin": {"pct_of_median": 64},
    }


# --- the file format -------------------------------------------------------

def test_a_post_round_trips():
    """write_post and read_post must agree, or the feed silently loses posts."""
    with tempfile.TemporaryDirectory() as d:
        path = SITE.write_post("09/08/26 5:04am: Its Tuesday.\n\nDry today.",
                               bundle(snow=7200), "school_call", out_dir=d)
        back = SITE.read_post(path)
        assert back["title"] == "Snow line near 7,200 ft"
        assert back["forDate"] == "2026-09-08"
        assert back["snowLineFt"] == 7200
        assert back["postType"] == "school_call"
        assert back["body"].startswith("09/08/26 5:04am:")
        assert "Dry today." in back["body"]
        assert back["sources"] == ["NWS GJT", "Open-Meteo"]


def test_titles_carry_no_em_dash():
    """These become page titles. The punctuation rule applies to the chrome."""
    for pt in ("school_call", "evening", "storm_setup", "totals"):
        for b in (bundle(), bundle(snow=8100)):
            t = SITE.auto_title(b, pt)
            assert "—" not in t and "–" not in t, t
    alerted = bundle()
    alerted["alerts"] = [{"event": "Winter Storm Warning"}]
    assert "—" not in SITE.auto_title(alerted, "school_call")


def test_slug_is_dated_and_url_safe():
    with tempfile.TemporaryDirectory() as d:
        path = SITE.write_post("body text here, long enough to be real",
                               bundle(snow=7200), out_dir=d)
        name = os.path.basename(path)
        assert name.startswith("2026-09-08-")
        assert name.endswith(".md")
        assert " " not in name and name.lower() == name
        # The comma in "7,200 ft" must not survive into the URL as a hyphen:
        # .../snow-line-near-7-200-ft splits the number and the keyword.
        assert "7200" in name and "7-200" not in name


# --- the feed, which is the whole transport --------------------------------

def test_feed_holds_every_post_newest_first():
    with tempfile.TemporaryDirectory() as d:
        for day in ("2026-09-06", "2026-09-08", "2026-09-07"):
            SITE.write_post(f"post for {day}, with enough body to be real",
                            bundle(day, snow=7000), out_dir=d)
        SITE.rebuild_feed(d)
        feed = json.load(open(os.path.join(d, "feed.json")))
        assert feed["count"] == 3
        assert not feed["truncated"]
        assert [p["forDate"] for p in feed["posts"]] == [
            "2026-09-08", "2026-09-07", "2026-09-06"]
        # The body must be IN the feed. One request is the entire point; if the
        # site has to fetch each post it hits an unauthenticated rate limit
        # shared with every other build on that runner.
        assert all(p["body"] for p in feed["posts"])


def test_feed_is_capped_but_the_markdown_is_not():
    with tempfile.TemporaryDirectory() as d:
        for i in range(8):
            SITE.write_post(f"body number {i}, long enough to count as a post",
                            bundle(f"2026-08-{i + 10:02d}", snow=7000 + i),
                            out_dir=d)
        SITE.rebuild_feed(d, limit=3)
        feed = json.load(open(os.path.join(d, "feed.json")))
        assert len(feed["posts"]) == 3
        assert feed["count"] == 8
        assert feed["truncated"] is True
        assert len([n for n in os.listdir(d) if n.endswith(".md")]) == 8


def test_rebuilding_is_idempotent_and_reflects_deletions():
    """The files are the source of truth, not an append-only log."""
    with tempfile.TemporaryDirectory() as d:
        p1 = SITE.write_post("first post body, long enough", bundle("2026-09-07"),
                             out_dir=d)
        SITE.write_post("second post body, long enough", bundle("2026-09-08"),
                        out_dir=d)
        SITE.rebuild_feed(d)
        assert json.load(open(os.path.join(d, "feed.json")))["count"] == 2
        os.remove(p1)
        SITE.rebuild_feed(d)
        feed = json.load(open(os.path.join(d, "feed.json")))
        assert feed["count"] == 1
        assert feed["posts"][0]["forDate"] == "2026-09-08"


# --- the approval path -----------------------------------------------------

def test_a_staged_draft_stays_out_of_the_feed():
    """This is the safety property. A held draft must not reach the public."""
    with tempfile.TemporaryDirectory() as d:
        SITE.write_post("published body, long enough", bundle("2026-09-07"),
                        out_dir=d)
        SITE.stage("held body, long enough to be real", bundle("2026-09-08"),
                   out_dir=d)
        SITE.rebuild_feed(d)
        feed = json.load(open(os.path.join(d, "feed.json")))
        assert feed["count"] == 1
        assert feed["posts"][0]["forDate"] == "2026-09-07"
        assert SITE.list_pending(d), "the held draft should still be staged"


def test_promoting_publishes_the_exact_reviewed_text():
    """Recomposing later would publish something nobody read."""
    with tempfile.TemporaryDirectory() as d:
        body = "the exact words a human read and approved, at length"
        SITE.stage(body, bundle("2026-09-08"), out_dir=d)
        result = SITE.promote("2026-09-08", d)
        assert os.path.exists(result["post"])
        assert not SITE.list_pending(d)
        feed = json.load(open(os.path.join(d, "feed.json")))
        assert feed["count"] == 1
        assert body in feed["posts"][0]["body"]


def test_promoting_something_that_is_not_staged_says_so():
    with tempfile.TemporaryDirectory() as d:
        try:
            SITE.promote("2026-01-01", d)
            assert False, "should have raised"
        except FileNotFoundError as exc:
            assert "2026-01-01" in str(exc)


# --- the self-correcting rewrite -------------------------------------------

def test_a_wording_block_is_retryable_and_a_data_block_is_not():
    assert G.text_fixable(["draft states a present-tense road surface condition"])
    assert not G.text_fixable(
        ["forecast unavailable for band(s): ['durango'] -- a partial forecast"])
    assert not G.text_fixable(
        ["required source(s) unavailable: ['alerts']"])
    assert not G.text_fixable([])


def test_the_rewrite_turns_the_real_2026_09_08_block_into_a_post():
    """The actual failure, end to end.

    A complete on-time forecast was blocked over one sentence and the morning
    went silent. The rewrite has to recover it.
    """
    from wx import run_forecast as RF
    from test_end_to_end import fake_fetchers
    from wx import bundle as B

    blocked = (
        "09/08/26 5:04am: Its Tuesday and the bus run looks fine. The gauge "
        "stayed dry overnight. Durango and the Valley stay dry all day, mid "
        "60s climbing to the mid 80s. Bayfield and up the Pine the same, upper "
        "50s to low 80s. Vallecito and the Florida start mid 50s. The high "
        "Weminuche sits in the upper 40s. The passes are dry. Coal Bank, Molas "
        "and Red Mountain all look good, and Wolf Creek stays clear too. "
        "Districts decide by 6:30. How is it looking where you are?")
    fixed = blocked.replace(
        "The passes are dry. Coal Bank, Molas and Red Mountain all look good, "
        "and Wolf Creek stays clear too.",
        "Coal Bank, Molas and Red Mountain should all stay dry through the "
        "morning, and Wolf Creek looks the same. Check CDOT for status.")

    calls = []

    def llm(messages):
        calls.append(messages)
        return fixed if len(calls) > 1 else blocked

    b = B.build(fetchers=fake_fetchers())
    with tempfile.TemporaryDirectory() as d:
        os.environ["WX_STATE_DIR"] = d
        os.environ["WX_SITE_DIR"] = os.path.join(d, "site")
        # run() writes output/ relative to the working directory. conftest
        # restores it afterwards.
        os.chdir(d)
        try:
            rc = RF.run(slot="school_call", llm=llm, first_30_days=False,
                        dry_bundle=b)
        finally:
            os.environ.pop("WX_STATE_DIR", None)
            os.environ.pop("WX_SITE_DIR", None)
        assert rc == 0
        assert len(calls) == 2, "should have rewritten exactly once"
        # The correction has to name the actual complaint, not just cite a rule.
        second = json.dumps(calls[1])
        assert "road surface" in second
        # And the recovered post has to reach the site.
        feed_path = os.path.join(d, "site", "feed.json")
        assert os.path.exists(feed_path), os.listdir(d)
        feed = json.load(open(feed_path))
        assert feed["count"] == 1
        assert "should all stay dry" in feed["posts"][0]["body"]


def test_a_data_block_does_not_burn_a_second_model_call():
    from wx import run_forecast as RF
    calls = []

    def llm(messages):
        calls.append(messages)
        return ("09/08/26 5:04am: Its Tuesday. " + "Dry everywhere today. " * 12)

    broken = {
        "missing": [], "post_for_date": "2026-09-08", "local_date": "2026-09-08",
        "generated_at": "2026-09-08T05:05:00-06:00",
        "bands": {"durango": {"ok": False}, "bayfield": {"ok": True},
                  "vallecito": {"ok": True}, "weminuche": {"ok": True}},
        "life_safety_alerts": [], "alerts": [], "snow_line": None,
    }
    with tempfile.TemporaryDirectory() as d:
        os.environ["WX_STATE_DIR"] = d
        os.chdir(d)
        try:
            RF.run(slot="school_call", llm=llm, first_30_days=False,
                   dry_bundle=broken)
        finally:
            os.environ.pop("WX_STATE_DIR", None)
    assert len(calls) <= 1
