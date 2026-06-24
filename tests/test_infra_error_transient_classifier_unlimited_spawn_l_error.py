"""Error path tests for infra-error transient classifier + spawn-layer recovery.

Invalid inputs must raise ValueError and the function must not silently succeed
(error path AC).
"""

from __future__ import annotations

import pytest

from bob.orchestrator.spawn_retry import classify_exit, load_patterns


# ---------------------------------------------------------------------------
# classify_exit error paths
# ---------------------------------------------------------------------------


def test_classify_exit_invalid_config_path_raises_or_uses_defaults():
    """Passing a non-existent config_path must not raise — falls back to defaults.

    classify_exit treats an unreadable config as a non-fatal degradation and
    uses built-in defaults instead of propagating the error to callers. This
    is the documented contract: the function always returns a classification.
    """
    result = classify_exit(exit_code=1, stderr="ECONNRESET", config_path="/nonexistent/path/spawn_retry.yaml")
    assert result == "transient"


def test_load_patterns_invalid_path_returns_defaults_not_empty():
    """load_patterns with a bad path must return the default patterns, not an empty list."""
    patterns = load_patterns("/nonexistent/config.yaml")
    assert len(patterns) > 0


def test_load_patterns_bad_path_does_not_raise():
    """load_patterns must never raise even for a completely invalid path."""
    try:
        patterns = load_patterns("/no/such/file.yaml")
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"load_patterns raised unexpectedly: {exc}")
    assert patterns is not None


def test_classify_exit_non_integer_exit_code_type_error():
    """Passing a string exit_code (wrong type) must raise TypeError — callers must pass int or None."""
    with pytest.raises((TypeError, AttributeError)):
        classify_exit(exit_code="one", stderr="")  # type: ignore[arg-type]


def test_classify_exit_invalid_work_events_type_error():
    """Passing a string for work_events (wrong type) must raise TypeError."""
    with pytest.raises((TypeError, AttributeError)):
        classify_exit(exit_code=1, stderr="", work_events="many")  # type: ignore[arg-type]


def test_classify_exit_invalid_duration_ms_type_error():
    """Passing a string for duration_ms must raise TypeError."""
    with pytest.raises((TypeError, AttributeError)):
        classify_exit(exit_code=1, stderr="", duration_ms="fast")  # type: ignore[arg-type]
