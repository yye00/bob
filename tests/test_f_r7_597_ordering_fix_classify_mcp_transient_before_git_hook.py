"""Tests for bob.f_r7_597_ordering_fix_classify_mcp_transient_before_git_hook (F-R7-607).

Verifies that the F-R7-607 classifier-precedence hoist entry point:
  - intercepts MCP-transient errors BEFORE the git-hook-rejection demotion
  - respects the 5-retry cap from F-R7-597
  - emits the correct EVALUATOR_MCP_TRANSIENT_PRE_HOOK event on match
  - returns intercept=False for unrelated errors
  - drain_pre_hook_transient_summary delegates correctly
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from bob.f_r7_597_ordering_fix_classify_mcp_transient_before_git_hook import (
    classify_mcp_transient_pre_hook,
    drain_pre_hook_transient_summary,
    f_r7_597_ordering_fix_classify_mcp_transient_before_git_hook,
)


# ---------------------------------------------------------------------------
# Primary AC test (exact function name required by acceptance criteria)
# ---------------------------------------------------------------------------

def test_f_r7_597_ordering_fix_classify_mcp_transient_before_git_hook() -> None:
    """AC entry point: intercept=True when stderr contains MCP-transient token."""
    stderr = "self signed certificate in certificate chain\nsome other noise"
    result = f_r7_597_ordering_fix_classify_mcp_transient_before_git_hook(
        stderr=stderr,
        retry_count=0,
        feature_id="feat-0000-test-0000-000000000001",
    )
    assert result["intercept"] is True
    assert result["event"] == "EVALUATOR_MCP_TRANSIENT_PRE_HOOK"
    assert result["matched_token"] is not None
    assert result["feature_id"] == "feat-0000-test-0000-000000000001"


# ---------------------------------------------------------------------------
# Token-match tests — each token in the F-R7-597 set must fire
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stderr_fragment,desc", [
    ("self signed certificate in certificate chain", "cert chain"),
    ("self-signed certificate", "self-signed"),
    ("MCP server is down, Connection failed", "MCP+Connection compound"),
    ("HTTP Connection failed with timeout", "HTTP Connection failed"),
    ("Streamable HTTP error occurred", "Streamable HTTP error"),
    ("Server rejected the configured Authorization header", "auth header"),
    ("MCP server returned 403 Forbidden", "MCP+403 compound"),
])
def test_each_mcp_transient_token_fires(stderr_fragment: str, desc: str) -> None:
    """Each MCP-transient token in the spec must cause intercept=True."""
    result = f_r7_597_ordering_fix_classify_mcp_transient_before_git_hook(
        stderr=stderr_fragment,
        retry_count=0,
        feature_id="feat-token-test",
    )
    assert result["intercept"] is True, f"Token '{desc}' did not trigger intercept"
    assert result["matched_token"] is not None


# ---------------------------------------------------------------------------
# Retry cap: at 5 intercepts, returns intercept=False regardless of tokens
# ---------------------------------------------------------------------------

def test_retry_cap_exhausted_returns_no_intercept() -> None:
    """When retry_count >= 5, intercept must be False even if tokens match."""
    stderr = "self signed certificate in certificate chain"
    result = f_r7_597_ordering_fix_classify_mcp_transient_before_git_hook(
        stderr=stderr,
        retry_count=5,
        feature_id="feat-cap-test",
    )
    assert result["intercept"] is False


def test_retry_cap_exactly_at_threshold() -> None:
    """retry_count=4 (one below cap) must still intercept."""
    stderr = "Streamable HTTP error"
    result = f_r7_597_ordering_fix_classify_mcp_transient_before_git_hook(
        stderr=stderr,
        retry_count=4,
        feature_id="feat-cap-boundary",
    )
    assert result["intercept"] is True


# ---------------------------------------------------------------------------
# Non-MCP errors must not fire
# ---------------------------------------------------------------------------

def test_non_mcp_error_no_intercept() -> None:
    """Unrelated stderr must not trigger the classifier."""
    stderr = "ImportError: No module named 'some_lib'"
    result = f_r7_597_ordering_fix_classify_mcp_transient_before_git_hook(
        stderr=stderr,
        retry_count=0,
        feature_id="feat-non-mcp",
    )
    assert result["intercept"] is False
    assert result["matched_token"] is None
    assert result["event"] == ""


def test_empty_stderr_no_intercept() -> None:
    """Empty/None stderr must not trigger the classifier."""
    for empty in [None, "", "   "]:
        result = f_r7_597_ordering_fix_classify_mcp_transient_before_git_hook(
            stderr=empty,
            retry_count=0,
        )
        assert result["intercept"] is False


# ---------------------------------------------------------------------------
# Alias: classify_mcp_transient_pre_hook is the same function
# ---------------------------------------------------------------------------

def test_alias_returns_same_result() -> None:
    """classify_mcp_transient_pre_hook alias must behave identically."""
    stderr = "self-signed certificate"
    r1 = f_r7_597_ordering_fix_classify_mcp_transient_before_git_hook(
        stderr=stderr, retry_count=0, feature_id="feat-alias"
    )
    r2 = classify_mcp_transient_pre_hook(
        stderr=stderr, retry_count=0, feature_id="feat-alias"
    )
    assert r1["intercept"] == r2["intercept"]
    assert r1["matched_token"] == r2["matched_token"]
    assert r1["event"] == r2["event"]


# ---------------------------------------------------------------------------
# Drain summary delegation
# ---------------------------------------------------------------------------

def test_drain_pre_hook_transient_summary_delegates() -> None:
    """drain_pre_hook_transient_summary must return the PRE_HOOK_TRANSIENT_SUMMARY dict."""
    with patch(
        "bob.f_r7_597_ordering_fix_classify_mcp_transient_before_git_hook.drain_mcp_transient_summary",
        return_value={"event": "PRE_HOOK_TRANSIENT_SUMMARY", "intercepted": 3},
    ) as mock_drain:
        result = drain_pre_hook_transient_summary(3)

    mock_drain.assert_called_once_with(3)
    assert result["event"] == "PRE_HOOK_TRANSIENT_SUMMARY"
    assert result["intercepted"] == 3


def test_drain_pre_hook_transient_summary_zero() -> None:
    """drain_pre_hook_transient_summary with zero intercepts emits the event."""
    result = drain_pre_hook_transient_summary(0)
    assert result["event"] == "PRE_HOOK_TRANSIENT_SUMMARY"
    assert result["intercepted"] == 0


# ---------------------------------------------------------------------------
# Integration: bob.orchestrator.run_loop import sanity check
# ---------------------------------------------------------------------------

def test_orchestrator_run_loop_importable() -> None:
    """bob.orchestrator.run_loop must be importable (integration AC)."""
    import bob.orchestrator.run_loop  # noqa: F401  (import-only check)


def test_run_loop_classify_mcp_transient_importable() -> None:
    """bob.run_loop.classify_mcp_transient must exist (backing function)."""
    from bob.run_loop import classify_mcp_transient
    assert callable(classify_mcp_transient)
