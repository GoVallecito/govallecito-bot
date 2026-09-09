"""
Shared test isolation.

WHY THIS EXISTS. test_runners.py does `os.chdir(d)` inside a
TemporaryDirectory context in ten places and never changes back. When the
context exits the directory is deleted, so the process is left sitting in a
directory that no longer exists. Every test that runs afterwards and touches a
relative path is then at the mercy of collection order: `os.makedirs("output")`
raises FileNotFoundError, and even `os.getcwd()` raises.

That had been latent for the whole life of the suite and only surfaced when a
new test happened to be ordered after those. It is the same shape as the bug
that let a test fixture overwrite a real draft, and the same shape as verify.py
writing the live snow-line calibration during a test run: state that leaks out
of the test that created it.

Fixing it here rather than in ten call sites means a new test cannot
reintroduce it.
"""
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def restore_working_directory():
    """Every test starts and ends in a directory that exists."""
    try:
        before = os.getcwd()
    except (FileNotFoundError, OSError):
        # A previous test left us somewhere deleted. Recover rather than fail
        # the innocent test that happened to be next.
        before = REPO_ROOT
    os.chdir(before if os.path.isdir(before) else REPO_ROOT)
    yield
    target = before if os.path.isdir(before) else REPO_ROOT
    os.chdir(target)
