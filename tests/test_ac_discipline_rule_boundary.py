"""Boundary/edge-case tests for enforce_ac_discipline.

Verifies that empty, zero, or minimum inputs return well-defined results
rather than raising exceptions (boundary case AC).
"""

from __future__ import annotations

from bob3.verifier_extension_ac_enforcer import (
    VERIFIER_EXTENSION_MODULES,
    enforce_ac_discipline,
)

_VERIFIER_TARGET = "src/bob3/enhanced_verification.py"
_NORMAL_TARGET = "src/bob3/some_unrelated_module.py"


def test_empty_acs_verifier_extension_returns_empty():
    """Empty AC list for a verifier-extension target returns empty filtered list without error."""
    result = enforce_ac_discipline([], _VERIFIER_TARGET, feature_id="boundary-empty-verifier")
    assert result.filtered_acs == []
    assert result.demoted == []
    assert result.is_verifier_extension is True


def test_empty_acs_normal_feature_returns_empty():
    """Empty AC list for a normal feature target returns empty filtered list without error."""
    result = enforce_ac_discipline([], _NORMAL_TARGET, feature_id="boundary-empty-normal")
    assert result.filtered_acs == []
    assert result.demoted == []
    assert result.is_verifier_extension is False


def test_empty_primary_diff_target_returns_unchanged():
    """Empty string primary_diff_target is treated as non-verifier-extension."""
    acs = ["behavior: some behavior"]
    result = enforce_ac_discipline(acs, "", feature_id="boundary-empty-target")
    assert result.is_verifier_extension is False
    assert result.filtered_acs == acs
    assert result.demoted == []


def test_single_non_behavior_ac_passes_through():
    """A single structural AC for a verifier-extension target passes through unchanged."""
    acs = ["structural: src/bob3/enhanced_verification.py contains function foo"]
    result = enforce_ac_discipline(acs, _VERIFIER_TARGET, feature_id="boundary-single-structural")
    assert result.filtered_acs == acs
    assert result.demoted == []
    assert result.is_verifier_extension is True


def test_single_behavior_ac_gets_demoted():
    """A single behavior AC for a verifier-extension target gets demoted (minimum case)."""
    acs = ["behavior: output MUST contain X"]
    result = enforce_ac_discipline(acs, _VERIFIER_TARGET, feature_id="boundary-single-behavior")
    assert len(result.demoted) == 1
    assert result.is_verifier_extension is True
    assert len(result.filtered_acs) == 1
    assert "[SKIP" in result.filtered_acs[0]


def test_no_feature_id_does_not_raise():
    """Calling without feature_id (None default) does not raise."""
    result = enforce_ac_discipline(["behavior: test"], _VERIFIER_TARGET)
    assert result.is_verifier_extension is True


def test_verifier_extension_modules_constant_is_non_empty():
    """VERIFIER_EXTENSION_MODULES is a non-empty tuple of strings."""
    assert isinstance(VERIFIER_EXTENSION_MODULES, tuple)
    assert len(VERIFIER_EXTENSION_MODULES) > 0
    for path in VERIFIER_EXTENSION_MODULES:
        assert isinstance(path, str)
        assert len(path) > 0


def test_all_non_behavior_acs_pass_through_verifier_extension():
    """A list containing only structural and integration ACs passes through unchanged."""
    acs = [
        "structural: file X contains regex Y",
        "integration: pytest tests/test_foo.py::test_bar passes",
        "pytest: tests/test_baz.py",
    ]
    result = enforce_ac_discipline(acs, _VERIFIER_TARGET, feature_id="boundary-no-behavior")
    assert result.filtered_acs == acs
    assert result.demoted == []
    assert result.is_verifier_extension is True


def test_behavior_ac_case_insensitive_prefix_is_caught():
    """'BEHAVIOR:' and 'Behavior:' prefixes are also caught by the rule."""
    acs_upper = ["BEHAVIOR: uppercase behavior AC"]
    acs_mixed = ["Behavior: mixed case behavior AC"]
    for acs in (acs_upper, acs_mixed):
        result = enforce_ac_discipline(acs, _VERIFIER_TARGET, feature_id="boundary-case")
        assert len(result.demoted) == 1, f"Expected demotion for: {acs[0]!r}"
