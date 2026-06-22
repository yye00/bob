"""Tests: enforce_maxfail_zero_when_xdist raises when xdist present without --maxfail=0."""

from __future__ import annotations

import pytest

from bob3.verifier.snapshot import (
    EarlyHaltMisconfigError,
    MAXFAIL_FLAG,
    enforce_maxfail_zero_when_xdist,
)


class TestEnforceMaxfailZeroWhenXdist:
    """enforce_maxfail_zero_when_xdist raises EarlyHaltMisconfigError when -n present but --maxfail=0 absent."""

    def test_raises_when_n_auto_without_maxfail_zero(self):
        argv = ["pytest", "-n", "auto", "tests/"]
        with pytest.raises(EarlyHaltMisconfigError):
            enforce_maxfail_zero_when_xdist(argv)

    def test_raises_when_n_int_without_maxfail_zero(self):
        argv = ["pytest", "-n", "4", "tests/"]
        with pytest.raises(EarlyHaltMisconfigError):
            enforce_maxfail_zero_when_xdist(argv)

    def test_raises_when_numprocesses_without_maxfail_zero(self):
        argv = ["pytest", "--numprocesses", "8", "tests/"]
        with pytest.raises(EarlyHaltMisconfigError):
            enforce_maxfail_zero_when_xdist(argv)

    def test_no_raise_when_n_present_and_maxfail_zero_present(self):
        argv = ["pytest", "--maxfail=0", "-n", "auto", "tests/"]
        enforce_maxfail_zero_when_xdist(argv)  # must not raise

    def test_no_raise_when_no_xdist_flags(self):
        argv = ["pytest", "tests/"]
        enforce_maxfail_zero_when_xdist(argv)  # must not raise

    def test_no_raise_when_no_xdist_flags_and_no_maxfail(self):
        argv = ["pytest", "-v", "tests/"]
        enforce_maxfail_zero_when_xdist(argv)  # must not raise; xdist not in use

    def test_error_message_mentions_xdist_and_maxfail(self):
        argv = ["pytest", "-n", "2", "tests/"]
        with pytest.raises(EarlyHaltMisconfigError, match="--maxfail=0"):
            enforce_maxfail_zero_when_xdist(argv)

    def test_maxfail_flag_constant_satisfies_check(self):
        argv = ["pytest", MAXFAIL_FLAG, "-n", "auto", "tests/"]
        enforce_maxfail_zero_when_xdist(argv)  # must not raise
