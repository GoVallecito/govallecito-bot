import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
from test_end_to_end import fake_fetchers
from wx import bundle as B, email_digest as ED, render_forecast_card as RC


def test_card_data_never_invents_a_number():
    b = B.build(fetchers=fake_fetchers())
    for k in b["bands"]:
        b["bands"][k]["summary"]["total_snow_in"] = 0.0
        b["bands"][k]["summary"]["total_precip_in"] = 0.0
    b["snow_line"] = None
    data = RC.card_data_from_bundle(b)
    assert all(v["amount"] == "dry" for v in data["bands"].values())
    assert data["snow_line_ft"] is None
    assert data["headline"] == "No precipitation expected"


def test_card_renders_wet_and_dry_days():
    b = B.build(fetchers=fake_fetchers())
    with tempfile.TemporaryDirectory() as d:
        wet = RC.render(RC.card_data_from_bundle(b), os.path.join(d, "wet.png"))
        assert os.path.getsize(wet) > 10_000
        b["snow_line"] = None
        b["precip_type_by_band"] = {}
        dry = RC.render(RC.card_data_from_bundle(b), os.path.join(d, "dry.png"))
        assert os.path.getsize(dry) > 10_000


def test_card_survives_an_absurd_elevation():
    # A bad freezing level must clamp, not draw off-card or crash the run.
    b = B.build(fetchers=fake_fetchers())
    data = RC.card_data_from_bundle(b)
    for ft in (100, 99_000):
        data["snow_line_ft"] = ft
        with tempfile.TemporaryDirectory() as d:
            assert os.path.getsize(RC.render(data, os.path.join(d, "x.png"))) > 5_000


def test_digest_subject_leads_with_the_alert():
    b = B.build(fetchers=fake_fetchers(life_safety=True))
    subject, plain, html = ED.render("11/04/26 5:52am: Morning.", b)
    assert subject.startswith("Winter Storm Warning")
    assert "BY ELEVATION" in plain
    assert "Up the Pine" in html


def test_digest_escapes_html():
    b = B.build(fetchers=fake_fetchers())
    _, _, html = ED.render("gusts <60mph & rising", b)
    assert "&lt;60mph &amp; rising" in html


def test_digest_refuses_to_bulk_send_over_smtp():
    r = ED.send("s", "p", "h", [f"a{i}@example.com" for i in range(200)])
    assert "skipped" in r and "list provider" in r["skipped"]


def test_digest_dry_run_sends_nothing():
    os.environ["DRY_RUN"] = "true"
    r = ED.send("s", "p", "h", ["a@example.com"])
    assert r.get("dry_run") is True
