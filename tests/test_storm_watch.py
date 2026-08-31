import datetime as _dt, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from wx import storm_watch as SW
from wx.sources import cdot as CD


def payload(hours=144, storm_at=None, intensity=0.12):
    """Synthetic multi-day payload. `storm_at` is the hour the storm starts."""
    t0 = _dt.datetime(2026, 11, 4, 0, 0)
    times, precip, snow = [], [], []
    for i in range(hours):
        times.append((t0 + _dt.timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M"))
        if storm_at is not None and storm_at <= i < storm_at + 12:
            precip.append(intensity)
            snow.append(intensity * 12)
        else:
            precip.append(0.0)
            snow.append(0.0)
    return {"hourly": {"time": times, "precipitation": precip, "snowfall": snow}}


def _fresh(tmp):
    SW.STATE = os.path.join(tmp, "storm_watch.json")


def test_quiet_pattern_does_not_fire():
    with tempfile.TemporaryDirectory() as d:
        _fresh(d)
        r = SW.evaluate({}, {"vallecito": payload()})
        assert r["fire"] is False and "below threshold" in r["reason"]


def test_storm_in_the_day_2_to_5_window_fires():
    with tempfile.TemporaryDirectory() as d:
        _fresh(d)
        r = SW.evaluate({}, {"vallecito": payload(storm_at=72)})
        assert r["fire"] is True, r["reason"]
        assert r["storm"]["liquid_in"] >= SW.MIN_LIQUID_IN


def test_storm_inside_48h_does_not_fire():
    # Inside two days the ordinary daily posts already cover it. Firing a
    # "setup" post for tonight's weather would just be noise.
    with tempfile.TemporaryDirectory() as d:
        _fresh(d)
        r = SW.evaluate({}, {"vallecito": payload(storm_at=6)})
        assert r["fire"] is False


def test_same_storm_does_not_fire_twice():
    with tempfile.TemporaryDirectory() as d:
        _fresh(d)
        p = {"vallecito": payload(storm_at=72)}
        assert SW.evaluate({}, p)["fire"] is True
        second = SW.evaluate({}, p)
        assert second["fire"] is False
        assert "not materially escalated" in second["reason"]


def test_materially_escalating_storm_fires_again():
    with tempfile.TemporaryDirectory() as d:
        _fresh(d)
        assert SW.evaluate({}, {"vallecito": payload(storm_at=72, intensity=0.05)})["fire"]
        big = SW.evaluate({}, {"vallecito": payload(storm_at=72, intensity=0.30)})
        assert big["fire"] is True and "escalated" in big["reason"]


def test_a_different_storm_fires_on_its_own():
    with tempfile.TemporaryDirectory() as d:
        _fresh(d)
        assert SW.evaluate({}, {"vallecito": payload(storm_at=72)})["fire"]
        later = SW.evaluate({}, {"vallecito": payload(storm_at=110)})
        assert later["fire"] is True


def test_state_file_is_bounded():
    with tempfile.TemporaryDirectory() as d:
        _fresh(d)
        for day in range(80):
            SW._save({"fired": {f"2026-{(day % 12) + 1:02d}-{(day % 28) + 1:02d}": {}}})
        for start in range(48, 130, 2):
            SW.evaluate({}, {"vallecito": payload(storm_at=start)})
        assert len(SW._load()["fired"]) <= 60


# --- CDOT -------------------------------------------------------------------

def test_cdot_without_a_key_degrades_cleanly():
    os.environ.pop("CDOT_API_KEY", None)
    r = CD.fetch_conditions()
    assert r.ok is False and "data.cotrip.org" in r.error


def test_cdot_groups_the_550_passes_as_one_unit():
    rows = [
        {"name": "US 550 Coal Bank Pass", "status": "Snow packed, traction law", "updated": None},
        {"name": "US 550 Molas Pass", "status": "Snow packed", "updated": None},
        {"name": "US 550 Red Mountain Pass", "status": "Closed for avalanche control", "updated": None},
        {"name": "US 160 Wolf Creek Pass", "status": "Wet", "updated": None},
    ]
    routes = CD._by_route(rows)
    assert routes["us550_north"]["summary"] == "closed"
    assert len(routes["us550_north"]["segments"]) == 3
    assert routes["us160_east"]["summary"] == "clear"


def test_pass_card_leads_with_the_closure():
    rows = [{"name": "US 550 Red Mountain Pass", "status": "Closed", "updated": None}]
    card = CD.format_pass_card(CD._by_route(rows))
    assert card.splitlines()[0].startswith("Short version:")
    assert "US-550 north" in card
    assert "close as a unit" in card
