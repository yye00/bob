"""Boundary case tests for F-R7-597 ordering fix — classify_mcp_transient.

AC: pytest: tests/test_f_r7_597_ordering_fix_boundary.py — empty, zero, or
minimum input returns a well-defined result rather than raising (boundary case)

Verifies that classify_mcp_transient (bob.run_loop) handles the minimum/empty
boundary inputs without crashing: None stderr, empty string, whitespace, zero
retry_count, and the exact cap boundary (retry_count=4 vs retry_count=5).
"""

from __future__ import annotations

import pytest

from bob.run_loop import classify_mcp_transient, drain_mcp_transient_summary


class TestBoundaryEmptyInputs:
    """Empty and None inputs must return a well-defined dict, never raise."""

    def test_none_stderr_returns_dict(self) -> None:
        result = classify_mcp_transient(stderr=None, retry_count=0)
        assert isinstance(result, dict)

    def test_none_stderr_intercept_is_false(self) -> None:
        result = classify_mcp_transient(stderr=None, retry_count=0)
        assert result["intercept"] is False

    def test_empty_string_stderr_returns_dict(self) -> None:
        result = classify_mcp_transient(stderr="", retry_count=0)
        assert isinstance(result, dict)

    def test_empty_string_stderr_intercept_is_false(self) -> None:
        result = classify_mcp_transient(stderr="", retry_count=0)
        assert result["intercept"] is False

    def test_whitespace_stderr_returns_dict(self) -> None:
        result = classify_mcp_transient(stderr="   \n\t  ", retry_count=0)
        assert isinstance(result, dict)

    def test_whitespace_stderr_intercept_is_false(self) -> None:
        result = classify_mcp_transient(stderr="   \n\t  ", retry_count=0)
        assert result["intercept"] is False


class TestBoundaryZeroRetryCount:
    """retry_count=0 is the minimum valid value — must not suppress matching."""

    def test_zero_retry_count_returns_dict(self) -> None:
        result = classify_mcp_transient(
            stderr="self signed certificate in certificate chain",
            retry_count=0,
        )
        assert isinstance(result, dict)

    def test_zero_retry_count_fires_on_matching_token(self) -> None:
        result = classify_mcp_transient(
            stderr="self signed certificate in certificate chain",
            retry_count=0,
        )
        assert result["intercept"] is True

    def test_zero_retry_count_no_match_returns_false(self) -> None:
        result = classify_mcp_transient(
            stderr="totally unrelated error",
            retry_count=0,
        )
        assert result["intercept"] is False


class TestBoundaryRetryCap:
    """Cap boundary: retry_count=4 intercepts; retry_count=5 does not."""

    def test_retry_count_4_below_cap_intercepts(self) -> None:
        result = classify_mcp_transient(
            stderr="Streamable HTTP error occurred",
            retry_count=4,
        )
        assert result["intercept"] is True

    def test_retry_count_5_at_cap_does_not_intercept(self) -> None:
        result = classify_mcp_transient(
            stderr="self signed certificate in certificate chain",
            retry_count=5,
        )
        assert result["intercept"] is False

    def test_retry_count_large_does_not_intercept(self) -> None:
        result = classify_mcp_transient(
            stderr="self signed certificate in certificate chain",
            retry_count=100,
        )
        assert result["intercept"] is False


class TestBoundaryResultShape:
    """Result dict always has required keys regardless of input."""

    @pytest.mark.parametrize("stderr,retry_count", [
        (None, 0),
        ("", 0),
        ("noise", 0),
        ("self signed certificate in certificate chain", 0),
        ("self signed certificate in certificate chain", 5),
    ])
    def test_result_always_has_intercept_key(self, stderr: str | None, retry_count: int) -> None:
        result = classify_mcp_transient(stderr=stderr, retry_count=retry_count)
        assert "intercept" in result

    @pytest.mark.parametrize("stderr,retry_count", [
        (None, 0),
        ("", 0),
        ("noise", 0),
    ])
    def test_result_always_has_matched_token_key(self, stderr: str | None, retry_count: int) -> None:
        result = classify_mcp_transient(stderr=stderr, retry_count=retry_count)
        assert "matched_token" in result

    @pytest.mark.parametrize("stderr,retry_count", [
        (None, 0),
        ("", 0),
        ("noise", 0),
    ])
    def test_result_always_has_event_key(self, stderr: str | None, retry_count: int) -> None:
        result = classify_mcp_transient(stderr=stderr, retry_count=retry_count)
        assert "event" in result


class TestBoundaryDrainSummary:
    """drain_mcp_transient_summary boundary: zero and large counts must return well-formed dicts."""

    def test_zero_intercepted_returns_dict(self) -> None:
        result = drain_mcp_transient_summary(intercepted=0)
        assert isinstance(result, dict)
        assert result["event"] == "PRE_HOOK_TRANSIENT_SUMMARY"
        assert result["intercepted"] == 0

    def test_one_intercepted_returns_dict(self) -> None:
        result = drain_mcp_transient_summary(intercepted=1)
        assert isinstance(result, dict)
        assert result["intercepted"] == 1

    def test_large_count_returns_dict(self) -> None:
        result = drain_mcp_transient_summary(intercepted=99_999)
        assert isinstance(result, dict)
        assert result["intercepted"] == 99_999
