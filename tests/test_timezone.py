"""
Guards against the timezone bug that silently emptied CoCoRaHS.

GitHub Actions runners are UTC. A job at 03:40 UTC is 21:40 the previous
evening in Colorado, so date.today() had already rolled over and the adapter
asked CoCoRaHS for a day whose observations do not exist yet. It returned an
empty result that looked exactly like a broken adapter, and the real cause was
invisible from the failure message.

Every date this product reasons about is a Mountain Time date: a snow day, an
observation date, a school-closure morning.
"""
import datetime as dt
import os
import pathlib
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from wx import constants as C

WX = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "wx"


def test_local_date_is_mountain_time_not_utc():
    assert C.local_date() == dt.datetime.now(ZoneInfo("America/Denver")).date()


def test_local_now_is_timezone_aware():
    assert C.local_now().tzinfo is not None, "a naive datetime is how this bug got in"


def test_no_module_uses_utc_today():
    """The regression guard proper.

    A single date.today() anywhere in this package reintroduces the bug for
    roughly six hours of every day - the evening hours, which is exactly when
    the school call is being prepared.
    """
    offenders = []
    for path in WX.rglob("*.py"):
        if path.name == "constants.py":
            continue          # defines the correct helpers
        text = path.read_text()
        for n, line in enumerate(text.splitlines(), 1):
            if "date.today()" in line and "local_date" not in line:
                offenders.append(f"{path.relative_to(WX)}:{n}: {line.strip()}")
    assert not offenders, (
        "use constants.local_date() instead of date.today():\n  " + "\n  ".join(offenders))


def test_no_module_uses_naive_now():
    offenders = []
    for path in WX.rglob("*.py"):
        if path.name == "constants.py":
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if "datetime.now()" in line and "local_now" not in line:
                offenders.append(f"{path.relative_to(WX)}:{n}: {line.strip()}")
    assert not offenders, (
        "use constants.local_now() instead of datetime.now():\n  " + "\n  ".join(offenders))


def test_cocorahs_window_is_wide_enough_for_late_entries():
    """Observers file through the day; a one-day window loses the stragglers."""
    import inspect
    from wx.sources import cocorahs
    sig = inspect.signature(cocorahs.fetch_reports)
    assert sig.parameters["days"].default >= 2
