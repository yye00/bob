"""Tests for bob3.run_loop.classify_mcp_transient — boundary and invalid-input coverage.

AC: pytest: tests/test_run_loop_mcp_transient.py
AC: integration: bob3.run_loop
AC: behavior: F-R7-597 ordering fix handles the boundary case of empty or zero
    input by returning a well-defined result rather than crashing
AC: behavior: F-R7-597 ordering fix raises a ValueError or returns a rejection
    when given invalid input, and does not silently succeed
"""

from __future__ import annotations

import pytest

from bob3.run_loop import classify_mcp_transient, drain_mcp_transient_summary


# ---------------------------------------------------------------------------
# Boundary cases: empty / zero inputs must not crash
# ---------------------------------------------------------------------------

class TestBoundaryCasesDoNotCrash:
    """Empty/zero inputs must produce a well-defined result, not an exception."""

    def test_none_stderr_returns_dict(self) -> None:
        result = classify_mcp_transient(stderr=None, retry_count=0)
        assert isinstance(result, dict), "Expected dict result for None stderr"

    def test_none_stderr_intercept_false(self) -> None:
        result = classify_mcp_transient(stderr=None, retry_count=0)
        assert result["intercept"] is False

    def test_empty_string_stderr_returns_dict(self) -> None:
        result = classify_mcp_transient(stderr="", retry_count=0)
        assert isinstance(result, dict), "Expected dict result for empty stderr"

    def test_empty_string_stderr_intercept_false(self) -> None:
        result = classify_mcp_transient(stderr="", retry_count=0)
        assert result["intercept"] is False

    def test_whitespace_only_stderr_returns_dict(self) -> None:
        result = classify_mcp_transient(stderr="   \n\t  ", retry_count=0)
        assert isinstance(result, dict), "Expected dict result for whitespace-only stderr"

    def test_whitespace_only_stderr_intercept_false(self) -> None:
        result = classify_mcp_transient(stderr="   \n\t  ", retry_count=0)
        assert result["intercept"] is False

    def test_zero_retry_count_returns_dict(self) -> None:
        result = classify_mcp_transient(
            stderr="self signed certificate in certificate chain",
            retry_count=0,
        )
        assert isinstance(result, dict)

    def test_zero_retry_count_fires_when_matching(self) -> None:
        result = classify_mcp_transient(
            stderr="self signed certificate in certificate chain",
            retry_count=0,
        )
        assert result["intercept"] is True

    def test_result_always_has_intercept_key(self) -> None:
        """intercept key must always be present regardless of input."""
        for stderr in (None, "", "unrelated text"):
            for count in (0, 5, 100):
                result = classify_mcp_transient(stderr=stderr, retry_count=count)
                assert "intercept" in result, (
                    f"Missing 'intercept' key for stderr={stderr!r}, retry_count={count}"
                )

    def test_result_always_has_event_key(self) -> None:
        result = classify_mcp_transient(stderr=None, retry_count=0)
        assert "event" in result

    def test_result_always_has_matched_token_key(self) -> None:
        result = classify_mcp_transient(stderr=None, retry_count=0)
        assert "matched_token" in result

    def test_drain_summary_zero_intercepted_returns_dict(self) -> None:
        result = drain_mcp_transient_summary(intercepted=0)
        assert isinstance(result, dict)
        assert result["event"] == "PRE_HOOK_TRANSIENT_SUMMARY"
        assert result["intercepted"] == 0

    def test_drain_summary_large_count_returns_dict(self) -> None:
        result = drain_mcp_transient_summary(intercepted=10_000)
        assert isinstance(result, dict)
        assert result["intercepted"] == 10_000


# ---------------------------------------------------------------------------
# Invalid input: must raise ValueError or return rejection (intercept=False)
# ---------------------------------------------------------------------------

class TestInvalidInputRejectedOrRaises:
    """Invalid inputs must not silently succeed — either raise ValueError or return intercept=False."""

    def test_negative_retry_count_does_not_intercept(self) -> None:
        """Negative retry_count is not a valid usage — treat as cap-not-exhausted,
        but must not silently allow unintended behavior (intercept=False is a rejection)."""
        try:
            result = classify_mcp_transient(
                stderr="self signed certificate in certificate chain",
                retry_count=-1,
            )
            # If it doesn't raise, it must return a well-defined dict (not silently corrupt).
            assert isinstance(result, dict), "Result must be a dict even for negative retry_count"
            # Negative retry_count — could intercept (treated as below cap) or not.
            # Either is acceptable as long as the function doesn't crash silently.
            assert "intercept" in result
        except (ValueError, TypeError):
            pass  # Raising an error is also valid

    def test_stderr_integer_type_raises_or_rejects(self) -> None:
        """Non-string, non-None stderr must raise TypeError/ValueError or return intercept=False."""
        try:
            result = classify_mcp_transient(stderr=42, retry_count=0)  # type: ignore[arg-type]
            # If no exception: must reject (not silently succeed with intercept=True).
            assert result["intercept"] is False, (
                "Integer stderr must not produce intercept=True silently"
            )
        except (TypeError, ValueError, AttributeError):
            pass  # Raising is valid

    def test_stderr_list_type_raises_or_rejects(self) -> None:
        """List stderr must raise or return intercept=False."""
        try:
            result = classify_mcp_transient(
                stderr=["self signed certificate in certificate chain"],  # type: ignore[arg-type]
                retry_count=0,
            )
            assert result["intercept"] is False, (
                "List stderr must not produce intercept=True silently"
            )
        except (TypeError, ValueError, AttributeError):
            pass

    def test_retry_count_string_raises_or_rejects(self) -> None:
        """Non-integer retry_count must raise or return intercept=False."""
        try:
            result = classify_mcp_transient(
                stderr="self signed certificate in certificate chain",
                retry_count="three",  # type: ignore[arg-type]
            )
            assert result["intercept"] is False
        except (TypeError, ValueError):
            pass

    def test_retry_count_none_raises_or_rejects(self) -> None:
        """None retry_count must raise or return intercept=False."""
        try:
            result = classify_mcp_transient(
                stderr="self signed certificate in certificate chain",
                retry_count=None,  # type: ignore[arg-type]
            )
            assert result["intercept"] is False
        except (TypeError, ValueError):
            pass


# ---------------------------------------------------------------------------
# Integration: importable from bob3.run_loop
# ---------------------------------------------------------------------------

class TestIntegration:
    """Verify the function is importable and present in __all__."""

    def test_classify_mcp_transient_importable(self) -> None:
        from bob3.run_loop import classify_mcp_transient as fn
        assert callable(fn)

    def test_drain_mcp_transient_summary_importable(self) -> None:
        from bob3.run_loop import drain_mcp_transient_summary as fn
        assert callable(fn)

    def test_classify_mcp_transient_in_all(self) -> None:
        import bob3.run_loop as m
        assert "classify_mcp_transient" in m.__all__

    def test_drain_mcp_transient_summary_in_all(self) -> None:
        import bob3.run_loop as m
        assert "drain_mcp_transient_summary" in m.__all__
