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

AND THE SECOND HALF OF THE SAME BUG. On POSIX, deleting the directory you are
standing in merely succeeds and leaves you nowhere, which is what the fixture
below cleans up after. On Windows it does not succeed at all: the kernel holds
a handle on any process's current directory, so `TemporaryDirectory.__exit__`
raises PermissionError [WinError 32] and the test fails inside its own
teardown, before a single assertion is read. Twelve tests failed that way and
none of them had anything wrong with the code they were testing.

The fixture below cannot fix that, because the deletion happens in the test
body, not in teardown. So the cwd has to be vacated a moment earlier -- at the
point of cleanup -- which is what the TemporaryDirectory subclass does. Same
argument as above: one place, not twelve call sites.
"""
import os
import tempfile

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _is_inside(directory, path):
    """True if `path` is `directory` or lives under it."""
    try:
        directory = os.path.normcase(os.path.realpath(directory))
        path = os.path.normcase(os.path.realpath(path))
    except OSError:
        return False
    return path == directory or path.startswith(directory + os.sep)


class _CwdSafeTemporaryDirectory(tempfile.TemporaryDirectory):
    """A TemporaryDirectory that steps out of itself before deleting itself.

    Windows refuses to remove a directory that is some process's cwd. Tests
    routinely chdir into these; stepping back to the repo root first makes the
    cleanup succeed there and changes nothing on POSIX, where the fixture below
    was already recovering from the same chdir.
    """

    def cleanup(self):
        try:
            here = os.getcwd()
        except OSError:
            here = None
        if here is None or _is_inside(self.name, here):
            os.chdir(REPO_ROOT)
        super().cleanup()


# Tests call `tempfile.TemporaryDirectory()` by attribute lookup at call time,
# and pytest imports conftest before any test module, so patching the module
# attribute reaches all of them.
tempfile.TemporaryDirectory = _CwdSafeTemporaryDirectory


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
