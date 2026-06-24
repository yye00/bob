"""Tests: assert_maxfail_zero_in_argv raises EarlyHaltMisconfigError on nonzero --maxfail."""

from __future__ import annotations

import pytest

from bob.verifier.snapshot import (
    EarlyHaltMisconfigError,
    MAXFAIL_FLAG,
    assert_maxfail_zero_in_argv,
)


class TestAssertMaxfailZeroInArgv:
    """assert_maxfail_zero_in_argv rejects any non-zero --maxfail value."""

    def test_raises_on_maxfail_1(self):
        with pytest.raises(EarlyHaltMisconfigError, match="maxfail"):
            assert_maxfail_zero_in_argv(["pytest", "--maxfail=1", "tests/"])

    def test_raises_on_maxfail_10(self):
        with pytest.raises(EarlyHaltMisconfigError, match="maxfail"):
            assert_maxfail_zero_in_argv(["pytest", "--maxfail=10", "tests/"])

    def test_raises_on_maxfail_25(self):
        with pytest.raises(EarlyHaltMisconfigError, match="maxfail"):
            assert_maxfail_zero_in_argv(["pytest", "--maxfail=25", "tests/"])

    def test_raises_on_maxfail_999(self):
        with pytest.raises(EarlyHaltMisconfigError, match="maxfail"):
            assert_maxfail_zero_in_argv(["pytest", "--maxfail=999", "tests/"])

    def test_does_not_raise_on_maxfail_zero(self):
        assert_maxfail_zero_in_argv(["pytest", "--maxfail=0", "tests/"])  # must not raise

    def test_does_not_raise_when_no_maxfail(self):
        assert_maxfail_zero_in_argv(["pytest", "tests/"])  # must not raise

    def test_does_not_raise_with_maxfail_flag_constant(self):
        assert_maxfail_zero_in_argv(["pytest", MAXFAIL_FLAG, "tests/"])  # must not raise

    def test_error_message_contains_maxfail_word(self):
        with pytest.raises(EarlyHaltMisconfigError) as exc_info:
            assert_maxfail_zero_in_argv(["pytest", "--maxfail=5"])
        assert "maxfail" in str(exc_info.value).lower()

    def test_raises_on_nonzero_in_middle_of_argv(self):
        argv = ["pytest", "-v", "--maxfail=3", "tests/", "-k", "foo"]
        with pytest.raises(EarlyHaltMisconfigError, match="maxfail"):
            assert_maxfail_zero_in_argv(argv)
