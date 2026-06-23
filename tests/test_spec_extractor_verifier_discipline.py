"""Tests for bob3.spec_extractor.reject_behavior_ac_for_verifier_extension.

Verifies that the AC discipline rule is enforced at spec-extraction time:
features whose primary diff target is a verifier-extension module MUST NOT
express behavior ACs.
"""

from __future__ import annotations

import pytest

from bob3.spec_extractor import (
    VERIFIER_EXTENSION_MODULES,
    ACFilterResult,
    DemotedAC,
    reject_behavior_ac_for_verifier_extension,
)

_VERIFIER_TARGET = "src/bob3/enhanced_verification.py"
_NORMAL_TARGET = "src/bob3/some_unrelated_module.py"


def test_function_is_importable():
    """reject_behavior_ac_for_verifier_extension is importable from bob3.spec_extractor."""
    assert callable(reject_behavior_ac_for_verifier_extension)


def test_behavior_ac_demoted_for_verifier_extension():
    """A behavior: AC is demoted when the primary diff target is a verifier-extension module."""
    acs = ["behavior: output MUST contain the expected value"]
    result = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
    assert isinstance(result, ACFilterResult)
    assert result.is_verifier_extension is True
    assert len(result.demoted) == 1
    assert isinstance(result.demoted[0], DemotedAC)
    assert result.demoted[0].original == acs[0]
    assert "[SKIP" in result.filtered_acs[0]


def test_behavior_ac_not_demoted_for_normal_feature():
    """A behavior: AC is NOT demoted when the primary diff target is not a verifier module."""
    acs = ["behavior: output MUST contain the expected value"]
    result = reject_behavior_ac_for_verifier_extension(acs, _NORMAL_TARGET)
    assert result.is_verifier_extension is False
    assert result.demoted == []
    assert result.filtered_acs == acs


def test_structural_ac_passes_through_for_verifier_extension():
    """A structural: AC passes through unchanged for a verifier-extension feature."""
    acs = ["structural: src/bob3/enhanced_verification.py contains function foo"]
    result = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
    assert result.is_verifier_extension is True
    assert result.filtered_acs == acs
    assert result.demoted == []


def test_integration_pytest_ac_passes_through_for_verifier_extension():
    """A pytest:/integration: AC passes through unchanged for a verifier-extension feature."""
    acs = ["pytest: tests/test_foo.py::test_bar"]
    result = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
    assert result.is_verifier_extension is True
    assert result.filtered_acs == acs
    assert result.demoted == []


def test_multiple_acs_mixed_demotion():
    """Only behavior: ACs are demoted; others pass through."""
    acs = [
        "structural: file exists",
        "behavior: output MUST be correct",
        "pytest: tests/test_foo.py",
        "behavior: another behavior AC",
    ]
    result = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
    assert result.is_verifier_extension is True
    assert len(result.demoted) == 2
    assert len(result.filtered_acs) == 4
    assert result.filtered_acs[0] == "structural: file exists"
    assert "[SKIP" in result.filtered_acs[1]
    assert result.filtered_acs[2] == "pytest: tests/test_foo.py"
    assert "[SKIP" in result.filtered_acs[3]


def test_feature_id_accepted_as_kwarg():
    """feature_id keyword argument is accepted without error."""
    result = reject_behavior_ac_for_verifier_extension(
        ["behavior: test"],
        _VERIFIER_TARGET,
        feature_id="test-feature-id",
    )
    assert result.is_verifier_extension is True
    assert len(result.demoted) == 1


def test_non_list_raises_value_error():
    """Non-list acceptance_criteria raises ValueError."""
    with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
        reject_behavior_ac_for_verifier_extension("not a list", _VERIFIER_TARGET)


def test_none_raises_value_error():
    """None acceptance_criteria raises ValueError."""
    with pytest.raises(ValueError):
        reject_behavior_ac_for_verifier_extension(None, _VERIFIER_TARGET)


def test_empty_list_returns_empty_result():
    """Empty AC list returns empty filtered list without error."""
    result = reject_behavior_ac_for_verifier_extension([], _VERIFIER_TARGET)
    assert result.filtered_acs == []
    assert result.demoted == []
    assert result.is_verifier_extension is True


def test_verifier_extension_modules_constant_accessible():
    """VERIFIER_EXTENSION_MODULES constant is accessible from bob3.spec_extractor."""
    assert isinstance(VERIFIER_EXTENSION_MODULES, tuple)
    assert len(VERIFIER_EXTENSION_MODULES) > 0
    assert all(isinstance(m, str) for m in VERIFIER_EXTENSION_MODULES)


def test_all_verifier_extension_modules_trigger_demotion():
    """Each path in VERIFIER_EXTENSION_MODULES triggers verifier-extension demotion."""
    for module_path in VERIFIER_EXTENSION_MODULES:
        result = reject_behavior_ac_for_verifier_extension(
            ["behavior: should do X"],
            module_path,
            feature_id="test-all-modules",
        )
        assert result.is_verifier_extension is True, (
            f"Expected is_verifier_extension=True for path: {module_path!r}"
        )
        assert len(result.demoted) == 1, (
            f"Expected 1 demoted AC for path: {module_path!r}"
        )


def test_empty_primary_diff_target_is_non_verifier():
    """Empty string primary_diff_target is treated as a non-verifier-extension feature."""
    result = reject_behavior_ac_for_verifier_extension(
        ["behavior: some behavior"], "", feature_id="test-empty-target"
    )
    assert result.is_verifier_extension is False
    assert result.demoted == []
