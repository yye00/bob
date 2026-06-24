"""Tests for bob3.spec_extractor AC discipline rule for verifier-extension features.

Verifies that the reject_behavior_ac_for_verifier_extension function enforces
the AC discipline rule at spec-extraction time: features whose primary diff
target is a verifier-extension module MUST NOT express behavior ACs.
"""

from __future__ import annotations

import pytest

from bob3.spec_extractor import (
    ACFilterResult,
    DemotedAC,
    VERIFIER_EXTENSION_MODULES,
    reject_behavior_ac_for_verifier_extension,
)

_VERIFIER_TARGET = "src/bob3/enhanced_verification.py"
_NORMAL_TARGET = "src/bob3/some_unrelated_module.py"


def test_function_importable_from_spec_extractor():
    """reject_behavior_ac_for_verifier_extension is importable from bob3.spec_extractor."""
    assert callable(reject_behavior_ac_for_verifier_extension)


def test_behavior_ac_rejected_for_verifier_extension():
    """behavior: AC is rejected when primary diff target is a verifier-extension module."""
    acs = ["behavior: output MUST contain the expected pattern"]
    result = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
    assert isinstance(result, ACFilterResult)
    assert result.is_verifier_extension is True
    assert len(result.demoted) == 1
    assert isinstance(result.demoted[0], DemotedAC)
    assert result.demoted[0].original == acs[0]
    assert "[SKIP" in result.filtered_acs[0]


def test_behavior_ac_not_rejected_for_normal_feature():
    """behavior: AC is NOT rejected when primary diff target is not a verifier module."""
    acs = ["behavior: output MUST contain the expected pattern"]
    result = reject_behavior_ac_for_verifier_extension(acs, _NORMAL_TARGET)
    assert result.is_verifier_extension is False
    assert result.demoted == []
    assert result.filtered_acs == acs


def test_structural_ac_passes_through():
    """structural: AC passes through unchanged for a verifier-extension target."""
    acs = ["structural: src/bob3/enhanced_verification.py contains function foo"]
    result = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
    assert result.filtered_acs == acs
    assert result.demoted == []
    assert result.is_verifier_extension is True


def test_integration_pytest_ac_passes_through():
    """pytest:/integration: AC passes through unchanged for a verifier-extension target."""
    acs = ["pytest: tests/test_foo.py::test_bar"]
    result = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
    assert result.filtered_acs == acs
    assert result.demoted == []
    assert result.is_verifier_extension is True


def test_multiple_behavior_acs_all_rejected():
    """Multiple behavior: ACs are all rejected for verifier-extension features."""
    acs = [
        "behavior: output MUST include warning",
        "structural: file X contains regex Y",
        "behavior: function MUST raise ValueError",
    ]
    result = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
    assert len(result.demoted) == 2
    assert result.is_verifier_extension is True
    assert "[SKIP" in result.filtered_acs[0]
    assert result.filtered_acs[1] == acs[1]
    assert "[SKIP" in result.filtered_acs[2]


def test_non_list_raises_value_error():
    """Passing a non-list for acceptance_criteria raises ValueError."""
    with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
        reject_behavior_ac_for_verifier_extension("not a list", _VERIFIER_TARGET)


def test_none_raises_value_error():
    """Passing None for acceptance_criteria raises ValueError."""
    with pytest.raises(ValueError):
        reject_behavior_ac_for_verifier_extension(None, _VERIFIER_TARGET)


def test_empty_list_returns_empty_result():
    """Empty AC list returns empty filtered list and empty demoted list."""
    result = reject_behavior_ac_for_verifier_extension([], _VERIFIER_TARGET)
    assert result.filtered_acs == []
    assert result.demoted == []
    assert result.is_verifier_extension is True


def test_verifier_extension_modules_constant_accessible():
    """VERIFIER_EXTENSION_MODULES is accessible from bob3.spec_extractor."""
    assert isinstance(VERIFIER_EXTENSION_MODULES, tuple)
    assert len(VERIFIER_EXTENSION_MODULES) > 0


def test_all_verifier_extension_modules_trigger_rejection():
    """Every path in VERIFIER_EXTENSION_MODULES triggers behavior AC rejection."""
    acs = ["behavior: must do something"]
    for module_path in VERIFIER_EXTENSION_MODULES:
        result = reject_behavior_ac_for_verifier_extension(acs, module_path)
        assert result.is_verifier_extension is True, f"Expected verifier extension for: {module_path}"
        assert len(result.demoted) == 1, f"Expected demotion for: {module_path}"


def test_feature_id_accepted_as_kwarg():
    """feature_id keyword argument is accepted without error."""
    result = reject_behavior_ac_for_verifier_extension(
        ["behavior: test"], _VERIFIER_TARGET, feature_id="test-feature-123"
    )
    assert result.is_verifier_extension is True


def test_empty_primary_diff_target_is_non_verifier():
    """Empty string primary_diff_target is treated as a non-verifier-extension."""
    acs = ["behavior: test"]
    result = reject_behavior_ac_for_verifier_extension(acs, "")
    assert result.is_verifier_extension is False
    assert result.filtered_acs == acs


def test_acfilterresult_and_demotedac_importable():
    """ACFilterResult and DemotedAC are importable from bob3.spec_extractor."""
    assert ACFilterResult is not None
    assert DemotedAC is not None


def test_warning_emitted_with_structural_suggestion(caplog):
    """A warning is logged when a behavior AC is rejected."""
    import logging
    acs = ["behavior: output MUST contain X"]
    with caplog.at_level(logging.WARNING):
        reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET, feature_id="warn-test")
    assert any("behavior AC demoted" in record.message or "AC discipline" in record.message
                for record in caplog.records)
