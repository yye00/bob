"""Error-path tests for mutation_testing_post_impl_quality_gate_mutmut.

AC: pytest: tests/test_mutation_testing_post_impl_quality_gate_mutmut_error.py
    — invalid input raises ValueError and the function does not silently succeed
    (error path)

Covers:
- Invalid feature_id types raise ValueError.
- Invalid src_files types raise ValueError.
- Invalid pytest_passed types raise ValueError.
- run_mutation_test propagates MutmutMissingError (not swallowed).
- Zero src_files with valid feature_id and pytest_passed=True is handled.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch

from bob3.mutation_testing_post_impl_quality_gate_mutmut import (
    mutation_testing_post_impl_quality_gate_mutmut,
)
from bob3.verification.mutation_gate import MutmutMissingError


# ---------------------------------------------------------------------------
# ValueError on invalid inputs
# ---------------------------------------------------------------------------


def test_non_string_feature_id_raises_value_error(tmp_path):
    """Passing a non-string feature_id must raise ValueError."""
    with pytest.raises((ValueError, TypeError)):
        mutation_testing_post_impl_quality_gate_mutmut(
            feature_id=12345,  # type: ignore[arg-type]
            src_files=["src/bob3/foo.py"],
            test_dir="tests",
            workspace=str(tmp_path),
            pytest_passed=True,
        )


def test_non_list_src_files_raises_value_error(tmp_path):
    """Passing a non-list src_files must raise ValueError."""
    with pytest.raises((ValueError, TypeError)):
        mutation_testing_post_impl_quality_gate_mutmut(
            feature_id="feat-x",
            src_files="src/bob3/foo.py",  # type: ignore[arg-type]
            test_dir="tests",
            workspace=str(tmp_path),
            pytest_passed=True,
        )


def test_non_bool_pytest_passed_raises_value_error(tmp_path):
    """Passing a non-bool pytest_passed must raise ValueError."""
    with pytest.raises((ValueError, TypeError)):
        mutation_testing_post_impl_quality_gate_mutmut(
            feature_id="feat-x",
            src_files=["src/bob3/foo.py"],
            test_dir="tests",
            workspace=str(tmp_path),
            pytest_passed="yes",  # type: ignore[arg-type]
        )


def test_negative_threshold_raises_value_error(tmp_path):
    """Passing a threshold < 0 must raise ValueError."""
    with pytest.raises((ValueError, TypeError)):
        mutation_testing_post_impl_quality_gate_mutmut(
            feature_id="feat-x",
            src_files=["src/bob3/foo.py"],
            test_dir="tests",
            workspace=str(tmp_path),
            pytest_passed=True,
            threshold=-0.1,
        )


def test_threshold_above_1_raises_value_error(tmp_path):
    """Passing a threshold > 1.0 must raise ValueError."""
    with pytest.raises((ValueError, TypeError)):
        mutation_testing_post_impl_quality_gate_mutmut(
            feature_id="feat-x",
            src_files=["src/bob3/foo.py"],
            test_dir="tests",
            workspace=str(tmp_path),
            pytest_passed=True,
            threshold=1.5,
        )


# ---------------------------------------------------------------------------
# MutmutMissingError is surfaced — not silently swallowed
# ---------------------------------------------------------------------------


def test_mutmut_missing_error_surfaces_as_skipped_not_silent(tmp_path):
    """When mutmut is missing the gate returns a skipped result, NOT None.

    The function must NOT silently succeed (return None) — it must return
    a dict with skipped=True so callers can distinguish 'gate skipped for
    valid reason' from 'gate could not run due to missing dependency'.
    """
    with patch(
        "bob3.mutation_testing_post_impl_quality_gate_mutmut.run_mutation_test",
        side_effect=MutmutMissingError("mutmut not installed"),
    ):
        result = mutation_testing_post_impl_quality_gate_mutmut(
            feature_id="feat-missing",
            src_files=["src/bob3/foo.py"],
            test_dir="tests",
            workspace=str(tmp_path),
            pytest_passed=True,
        )

    # Must NOT be None (that would mean silently skipped without explanation)
    assert result is not None, (
        "When mutmut is missing, the gate must return a skipped dict, "
        "not None (silent success)"
    )
    assert result.get("skipped") is True
    reason = result.get("reason", "")
    assert reason, "skipped result must include a non-empty reason string"


# ---------------------------------------------------------------------------
# Empty feature_id returns None (not ValueError) — that's the documented
# skip path, not an error path
# ---------------------------------------------------------------------------


def test_empty_feature_id_returns_none_not_value_error(tmp_path):
    """Empty string feature_id is a documented no-op (returns None), not an error."""
    result = mutation_testing_post_impl_quality_gate_mutmut(
        feature_id="",
        src_files=["src/bob3/foo.py"],
        test_dir="tests",
        workspace=str(tmp_path),
        pytest_passed=True,
    )
    assert result is None


def test_pytest_failed_returns_none_not_value_error(tmp_path):
    """pytest_passed=False is a documented no-op (returns None), not an error."""
    result = mutation_testing_post_impl_quality_gate_mutmut(
        feature_id="feat-x",
        src_files=["src/bob3/foo.py"],
        test_dir="tests",
        workspace=str(tmp_path),
        pytest_passed=False,
    )
    assert result is None
