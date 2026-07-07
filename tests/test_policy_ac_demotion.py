"""Tests for bob.policy_ac_demotion (f1d61aac).

Feature: Policy-AC demotion for cross-feature reference ACs
AC: pytest: tests/test_policy_ac_demotion.py

When a criterion body contains a token matching \\bF-R\\d+-\\d{3}\\b, the
demote_cross_feature_ac function demotes it to PASS with a WARNING record,
since per-feature verification cannot statically verify cross-feature policy
claims.
"""

from __future__ import annotations

import pathlib

import pytest


# ---------------------------------------------------------------------------
# Import checks
# ---------------------------------------------------------------------------


def test_module_importable():
    """bob.policy_ac_demotion must be importable."""
    import bob.policy_ac_demotion  # noqa: F401


def test_function_importable():
    """demote_cross_feature_ac must be importable from bob.policy_ac_demotion."""
    from bob.policy_ac_demotion import demote_cross_feature_ac

    assert callable(demote_cross_feature_ac)


# ---------------------------------------------------------------------------
# Core demotion behavior
# ---------------------------------------------------------------------------


def test_demotes_criterion_with_fr7_reference():
    """Criterion containing F-R7-478 is demoted to (True, reason)."""
    from bob.policy_ac_demotion import demote_cross_feature_ac

    criterion = "integration: F-R7-478 unlimited spawn-retry path remains unaffected"
    result = demote_cross_feature_ac(criterion)

    assert result is not None, "Expected demotion for cross-feature reference"
    passed, reason = result
    assert passed is True
    assert reason


def test_demotes_criterion_with_fr532_reference():
    """Criterion with F-R7-532 reference is demoted."""
    from bob.policy_ac_demotion import demote_cross_feature_ac

    criterion = "integration: regression-sweep / F-R7-532 invariant pass continues to run."
    result = demote_cross_feature_ac(criterion)

    assert result is not None
    passed, reason = result
    assert passed is True


def test_demotes_criterion_with_fr_high_number():
    """Criterion with F-R7-999 (high-numbered feature ref) is demoted."""
    from bob.policy_ac_demotion import demote_cross_feature_ac

    result = demote_cross_feature_ac("behavior: F-R7-999 must not be affected")
    assert result is not None
    assert result[0] is True


def test_no_demotion_for_normal_criterion():
    """Criterion without any F-RX-YYY token returns None (no demotion)."""
    from bob.policy_ac_demotion import demote_cross_feature_ac

    result = demote_cross_feature_ac("function defined: bob.some_module.some_fn")
    assert result is None


def test_no_demotion_for_file_exists_criterion():
    """File-exists criterion with no cross-feature ref returns None."""
    from bob.policy_ac_demotion import demote_cross_feature_ac

    result = demote_cross_feature_ac("file exists: src/bob/some_module.py")
    assert result is None


def test_reason_mentions_feature_token():
    """The demotion reason must reference the matched F-RX-YYY token."""
    from bob.policy_ac_demotion import demote_cross_feature_ac

    criterion = "integration: F-R7-478 path remains unaffected"
    result = demote_cross_feature_ac(criterion)

    assert result is not None
    _, reason = result
    assert "F-R7-478" in reason or "cross-feature" in reason.lower()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_empty_string_raises_value_error():
    """Empty string raises ValueError."""
    from bob.policy_ac_demotion import demote_cross_feature_ac

    with pytest.raises(ValueError):
        demote_cross_feature_ac("")


def test_none_raises_value_error():
    """None raises ValueError."""
    from bob.policy_ac_demotion import demote_cross_feature_ac

    with pytest.raises(ValueError):
        demote_cross_feature_ac(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# is_cross_feature_policy_ac predicate
# ---------------------------------------------------------------------------


def test_is_cross_feature_policy_ac_importable():
    """is_cross_feature_policy_ac must be importable from bob.policy_ac_demotion."""
    from bob.policy_ac_demotion import is_cross_feature_policy_ac

    assert callable(is_cross_feature_policy_ac)


def test_is_cross_feature_true_for_fr_reference():
    """A criterion containing an F-RX-YYY token is a cross-feature policy AC."""
    from bob.policy_ac_demotion import is_cross_feature_policy_ac

    assert is_cross_feature_policy_ac(
        "integration: F-R7-478 unlimited spawn-retry path remains unaffected"
    ) is True


def test_is_cross_feature_false_for_normal_criterion():
    """A criterion with no F-RX-YYY token is not a cross-feature policy AC."""
    from bob.policy_ac_demotion import is_cross_feature_policy_ac

    assert is_cross_feature_policy_ac("function defined: bob.mod.fn") is False


def test_is_cross_feature_empty_string_raises():
    """Empty string is invalid input — must raise ValueError."""
    from bob.policy_ac_demotion import is_cross_feature_policy_ac

    with pytest.raises(ValueError):
        is_cross_feature_policy_ac("")


def test_is_cross_feature_none_raises():
    """None is invalid input — must raise ValueError."""
    from bob.policy_ac_demotion import is_cross_feature_policy_ac

    with pytest.raises(ValueError):
        is_cross_feature_policy_ac(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Integration with bob.enhanced_verification
# ---------------------------------------------------------------------------


def test_integration_with_enhanced_verification():
    """demote_cross_feature_ac delegates to bob.enhanced_verification."""
    from bob.policy_ac_demotion import demote_cross_feature_ac
    from bob.enhanced_verification import demote_cross_feature_ac as ev_func

    criterion = "integration: F-R7-478 unlimited spawn-retry path remains unaffected"
    result_module = demote_cross_feature_ac(criterion)
    result_ev = ev_func(criterion)

    assert result_module == result_ev, (
        "policy_ac_demotion.demote_cross_feature_ac must delegate to enhanced_verification"
    )


def test_workspace_none_does_not_raise():
    """Passing workspace=None is valid and must not raise."""
    from bob.policy_ac_demotion import demote_cross_feature_ac

    result = demote_cross_feature_ac(
        "integration: F-R7-478 remains unaffected", workspace=None
    )
    assert result is not None
    assert result[0] is True
