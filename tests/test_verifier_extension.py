"""Tests for bob3.verifier_extension.reject_behavior_ac.

Verifies that reject_behavior_ac correctly enforces AC discipline for
verifier-extension features by integrating with bob3.spec_extractor.
"""

from __future__ import annotations

import pytest

from bob3.verifier_extension import (
    VERIFIER_EXTENSION_MODULES,
    ACFilterResult,
    DemotedAC,
    reject_behavior_ac,
)

_VERIFIER_TARGET = "src/bob3/enhanced_verification.py"
_NORMAL_TARGET = "src/bob3/some_unrelated_module.py"


def test_function_is_importable():
    """reject_behavior_ac is importable from bob3.verifier_extension."""
    assert callable(reject_behavior_ac)


def test_verifier_extension_modules_exported():
    """VERIFIER_EXTENSION_MODULES is exported from bob3.verifier_extension."""
    assert isinstance(VERIFIER_EXTENSION_MODULES, tuple)
    assert len(VERIFIER_EXTENSION_MODULES) > 0


def test_returns_ac_filter_result():
    """reject_behavior_ac returns an ACFilterResult instance."""
    result = reject_behavior_ac([], _VERIFIER_TARGET)
    assert isinstance(result, ACFilterResult)


def test_normal_feature_passes_through_unchanged():
    """For a non-verifier-extension target, all ACs pass through unchanged."""
    acs = ["behavior: some behavior", "structural: file X contains Y"]
    result = reject_behavior_ac(acs, _NORMAL_TARGET, feature_id="test-normal")
    assert result.filtered_acs == acs
    assert result.demoted == []
    assert result.is_verifier_extension is False


def test_verifier_extension_rejects_behavior_ac():
    """For a verifier-extension target, behavior ACs are rejected/demoted."""
    acs = ["behavior: output MUST contain X"]
    result = reject_behavior_ac(acs, _VERIFIER_TARGET, feature_id="test-reject")
    assert result.is_verifier_extension is True
    assert len(result.demoted) == 1
    assert isinstance(result.demoted[0], DemotedAC)
    assert result.demoted[0].original == acs[0]
    assert "[SKIP" in result.filtered_acs[0]


def test_structural_ac_passes_through_for_verifier_extension():
    """Structural ACs are not rejected for verifier-extension features."""
    acs = ["structural: src/bob3/enhanced_verification.py contains function foo"]
    result = reject_behavior_ac(acs, _VERIFIER_TARGET, feature_id="test-structural")
    assert result.filtered_acs == acs
    assert result.demoted == []
    assert result.is_verifier_extension is True


def test_integration_pytest_ac_passes_through_for_verifier_extension():
    """Integration pytest ACs are not rejected for verifier-extension features."""
    acs = ["integration: pytest tests/test_foo.py::test_bar passes"]
    result = reject_behavior_ac(acs, _VERIFIER_TARGET, feature_id="test-integration")
    assert result.filtered_acs == acs
    assert result.demoted == []
    assert result.is_verifier_extension is True


def test_mixed_acs_only_behavior_rejected():
    """Only behavior ACs are rejected; structural and integration ACs pass through."""
    acs = [
        "structural: file X contains Y",
        "behavior: output MUST contain Z",
        "integration: pytest tests/test_foo.py passes",
    ]
    result = reject_behavior_ac(acs, _VERIFIER_TARGET, feature_id="test-mixed")
    assert result.is_verifier_extension is True
    assert len(result.demoted) == 1
    assert result.demoted[0].original == "behavior: output MUST contain Z"
    assert len(result.filtered_acs) == 3
    assert result.filtered_acs[0] == acs[0]
    assert "[SKIP" in result.filtered_acs[1]
    assert result.filtered_acs[2] == acs[2]


def test_non_list_raises_value_error():
    """Passing a non-list for acceptance_criteria raises ValueError."""
    with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
        reject_behavior_ac("not a list", _VERIFIER_TARGET)


def test_none_raises_value_error():
    """Passing None raises ValueError."""
    with pytest.raises(ValueError):
        reject_behavior_ac(None, _VERIFIER_TARGET)


def test_empty_list_returns_empty_result():
    """Empty list returns empty ACFilterResult without error."""
    result = reject_behavior_ac([], _VERIFIER_TARGET)
    assert result.filtered_acs == []
    assert result.demoted == []
    assert result.is_verifier_extension is True


def test_no_feature_id_does_not_raise():
    """Calling without feature_id (default None) does not raise."""
    result = reject_behavior_ac(["behavior: test"], _VERIFIER_TARGET)
    assert result.is_verifier_extension is True


def test_integrates_with_spec_extractor():
    """reject_behavior_ac delegates to filter_behavior_acs_for_verifier_extension in spec_extractor."""
    from bob3.spec_quality.spec_extractor import filter_behavior_acs_for_verifier_extension

    acs = ["behavior: X", "structural: Y"]
    direct = filter_behavior_acs_for_verifier_extension(acs, _VERIFIER_TARGET)
    via_reject = reject_behavior_ac(acs, _VERIFIER_TARGET)

    assert direct.filtered_acs == via_reject.filtered_acs
    assert direct.is_verifier_extension == via_reject.is_verifier_extension
    assert len(direct.demoted) == len(via_reject.demoted)


def test_behavior_prefix_case_insensitive():
    """BEHAVIOR: and Behavior: prefixes are also caught."""
    for prefix in ("BEHAVIOR:", "Behavior:"):
        acs = [f"{prefix} some behavior"]
        result = reject_behavior_ac(acs, _VERIFIER_TARGET)
        assert len(result.demoted) == 1, f"Expected demotion for prefix {prefix!r}"
