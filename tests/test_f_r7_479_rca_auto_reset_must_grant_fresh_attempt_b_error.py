"""Error-path tests for F-R7-479: invalid input raises ValueError/TypeError, not silent success.

Verifies that the public API rejects invalid inputs with explicit exceptions rather
than swallowing errors or returning a misleading default result.
"""

from __future__ import annotations

import pytest

from bob.rca import classify_verification_failure_cause, should_grant_fresh_attempt_budget


# ---------------------------------------------------------------------------
# Error path: classify_verification_failure_cause
# ---------------------------------------------------------------------------


def test_classify_none_raises_value_error():
    """None input → ValueError (not silent success or AttributeError)."""
    with pytest.raises(ValueError):
        classify_verification_failure_cause(None)  # type: ignore[arg-type]


def test_classify_string_raises_type_error():
    """String input (not a list) → TypeError."""
    with pytest.raises(TypeError):
        classify_verification_failure_cause("behavior: foo returns bar")  # type: ignore[arg-type]


def test_classify_int_raises_type_error():
    """Integer input → TypeError."""
    with pytest.raises(TypeError):
        classify_verification_failure_cause(42)  # type: ignore[arg-type]


def test_classify_dict_raises_type_error():
    """Dict input → TypeError."""
    with pytest.raises(TypeError):
        classify_verification_failure_cause({"ac": "behavior: foo"})  # type: ignore[arg-type]


def test_classify_tuple_raises_type_error():
    """Tuple input → TypeError (only list is valid)."""
    with pytest.raises(TypeError):
        classify_verification_failure_cause(("behavior: foo",))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Error path: should_grant_fresh_attempt_budget
# ---------------------------------------------------------------------------


def test_grant_negative_attempts_raises_value_error():
    """Negative refinement_attempts → ValueError (invariant violation)."""
    with pytest.raises(ValueError):
        should_grant_fresh_attempt_budget("code_emission_defect", -1)


def test_grant_very_negative_attempts_raises_value_error():
    """Highly negative refinement_attempts → ValueError."""
    with pytest.raises(ValueError):
        should_grant_fresh_attempt_budget("code_emission_defect", -100)


def test_grant_string_attempts_raises_type_error():
    """String where int expected → TypeError."""
    with pytest.raises(TypeError):
        should_grant_fresh_attempt_budget("code_emission_defect", "3")  # type: ignore[arg-type]


def test_grant_float_attempts_raises_type_error():
    """Float where int expected → TypeError."""
    with pytest.raises(TypeError):
        should_grant_fresh_attempt_budget("code_emission_defect", 2.5)  # type: ignore[arg-type]


def test_grant_none_attempts_raises_type_error():
    """None where int expected → TypeError."""
    with pytest.raises(TypeError):
        should_grant_fresh_attempt_budget("code_emission_defect", None)  # type: ignore[arg-type]
