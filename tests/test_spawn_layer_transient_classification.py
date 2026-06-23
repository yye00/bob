"""Tests for spawn_layer.classify_exit transient classification.

Verifies that infra-error signatures (HTTP 429, rate-limit, ECONNRESET,
ETIMEDOUT, ENOENT) are classified as TRANSIENT by the spawn layer,
and that real failures and mid-work crashes are classified correctly.
"""

from __future__ import annotations

import pytest

from spawn_layer import classify_exit


# ---------------------------------------------------------------------------
# Transient classification
# ---------------------------------------------------------------------------


def test_classify_http_429_is_transient():
    """HTTP 429 rate-limit in stderr must be classified as transient."""
    result = classify_exit(exit_code=1, stderr="Error: 429 Too Many Requests rate limit exceeded")
    assert result == "transient"


def test_classify_rate_limit_is_transient():
    """'rate-limit' string in stderr must be classified as transient."""
    result = classify_exit(exit_code=1, stderr="claude: rate-limit hit, please retry")
    assert result == "transient"


def test_classify_econnreset_is_transient():
    """ECONNRESET in stderr must be classified as transient."""
    result = classify_exit(exit_code=1, stderr="connect ECONNRESET 127.0.0.1:443")
    assert result == "transient"


def test_classify_etimedout_is_transient():
    """ETIMEDOUT in stderr must be classified as transient."""
    result = classify_exit(exit_code=1, stderr="request timed out ETIMEDOUT")
    assert result == "transient"


def test_classify_enoent_claude_is_transient():
    """ENOENT referencing claude binary must be classified as transient."""
    result = classify_exit(exit_code=1, stderr="spawn ENOENT: no such file /usr/bin/claude")
    assert result == "transient"


def test_classify_deprecated_shared_key_is_transient():
    """Deprecated shared API key message must be classified as transient."""
    result = classify_exit(exit_code=1, stderr="This shared API key and is being deprecated")
    assert result == "transient"


# ---------------------------------------------------------------------------
# Real failure classification
# ---------------------------------------------------------------------------


def test_classify_zero_exit_code_is_real_failure():
    """exit_code=0 must always return real_failure (success path, caller handles)."""
    result = classify_exit(exit_code=0, stderr="")
    assert result == "real_failure"


def test_classify_implementation_error_is_real_failure():
    """An exit with no infra signals is a real failure."""
    result = classify_exit(exit_code=1, stderr="AssertionError: expected 42 got 0")
    assert result == "real_failure"


def test_classify_syntax_error_is_real_failure():
    """Python SyntaxError in stderr is not an infra signal — real failure."""
    result = classify_exit(exit_code=1, stderr="SyntaxError: invalid syntax at line 5")
    assert result == "real_failure"


# ---------------------------------------------------------------------------
# Mid-work crash classification
# ---------------------------------------------------------------------------


def test_classify_nonzero_work_events_is_mid_work_crash():
    """Non-zero work_events with no infra signals → mid_work_crash."""
    result = classify_exit(exit_code=1, stderr="unexpected shutdown", work_events=5, duration_ms=10000)
    assert result == "mid_work_crash"


def test_classify_work_events_with_duration_zero_is_transient():
    """work_events > 0 AND duration_ms == 0 is a JSONL race → transient."""
    result = classify_exit(exit_code=1, stderr="", work_events=3, duration_ms=0)
    assert result == "transient"


# ---------------------------------------------------------------------------
# Case-insensitivity
# ---------------------------------------------------------------------------


def test_classify_lowercase_econnreset_is_transient():
    """Pattern matching must be case-insensitive for ECONNRESET."""
    result = classify_exit(exit_code=1, stderr="econnreset detected")
    assert result == "transient"


def test_classify_uppercase_rate_limit_is_transient():
    """Pattern matching must be case-insensitive for RATE-LIMIT."""
    result = classify_exit(exit_code=1, stderr="RATE-LIMIT EXCEEDED")
    assert result == "transient"


# ---------------------------------------------------------------------------
# None / optional inputs
# ---------------------------------------------------------------------------


def test_classify_none_stderr_no_infra_markers_is_real_failure():
    """None stderr with no infra signals → real_failure (no crash)."""
    result = classify_exit(exit_code=1, stderr=None)
    assert result in ("transient", "mid_work_crash", "real_failure")


def test_classify_none_exit_code_none_stderr_no_raise():
    """None exit_code + None stderr must not raise."""
    result = classify_exit(exit_code=None, stderr=None)
    assert result in ("transient", "mid_work_crash", "real_failure")
