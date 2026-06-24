"""Tests for bob.verifier.ac_extractor.reject_behavior_ac_for_verifier_extensions.

Covers the AC discipline rule: verifier-extension features MUST NOT express
behavior ACs at spec-extraction time.
"""

from __future__ import annotations

import pytest

from bob.verifier.ac_extractor import (
    VERIFIER_EXTENSION_MODULES,
    ACFilterResult,
    DemotedAC,
    reject_behavior_ac_for_verifier_extensions,
)

_VERIFIER_TARGET = "src/bob/enhanced_verification.py"
_NORMAL_TARGET = "src/bob/some_other_module.py"


# ---------------------------------------------------------------------------
# Basic contract
# ---------------------------------------------------------------------------


def test_returns_ac_filter_result():
    """Return type is ACFilterResult."""
    result = reject_behavior_ac_for_verifier_extensions([], _VERIFIER_TARGET)
    assert isinstance(result, ACFilterResult)


def test_non_verifier_extension_passes_through():
    """Behavior ACs for non-verifier targets pass through untouched."""
    acs = ["behavior: the output MUST include X"]
    result = reject_behavior_ac_for_verifier_extensions(acs, _NORMAL_TARGET)
    assert result.is_verifier_extension is False
    assert result.filtered_acs == acs
    assert result.demoted == []


def test_verifier_extension_behavior_ac_demoted():
    """Behavior AC for a verifier-extension target is demoted."""
    acs = ["behavior: verifier MUST detect pattern Z"]
    result = reject_behavior_ac_for_verifier_extensions(acs, _VERIFIER_TARGET)
    assert result.is_verifier_extension is True
    assert len(result.demoted) == 1
    assert isinstance(result.demoted[0], DemotedAC)
    assert result.demoted[0].original == acs[0]


def test_verifier_extension_structural_ac_passes():
    """Structural ACs for verifier-extension targets pass through unchanged."""
    acs = ["structural: src/bob/enhanced_verification.py contains function foo"]
    result = reject_behavior_ac_for_verifier_extensions(acs, _VERIFIER_TARGET)
    assert result.is_verifier_extension is True
    assert result.filtered_acs == acs
    assert result.demoted == []


def test_verifier_extension_integration_ac_passes():
    """Integration/pytest ACs for verifier-extension targets pass through unchanged."""
    acs = ["pytest: tests/test_verifier.py::test_something"]
    result = reject_behavior_ac_for_verifier_extensions(acs, _VERIFIER_TARGET)
    assert result.is_verifier_extension is True
    assert result.filtered_acs == acs
    assert result.demoted == []


def test_mixed_acs_only_behavior_demoted():
    """Only behavior ACs are demoted; structural and integration ACs pass through."""
    acs = [
        "structural: file X exists",
        "behavior: output MUST contain Y",
        "pytest: tests/test_foo.py",
    ]
    result = reject_behavior_ac_for_verifier_extensions(acs, _VERIFIER_TARGET)
    assert result.is_verifier_extension is True
    assert len(result.demoted) == 1
    assert result.demoted[0].original == "behavior: output MUST contain Y"
    assert len(result.filtered_acs) == 3


def test_demoted_ac_replaced_with_skip_note():
    """Demoted behavior AC is replaced with a [SKIP...] string in filtered_acs."""
    acs = ["behavior: some unverifiable claim"]
    result = reject_behavior_ac_for_verifier_extensions(acs, _VERIFIER_TARGET)
    assert len(result.filtered_acs) == 1
    assert "[SKIP" in result.filtered_acs[0]


def test_multiple_behavior_acs_all_demoted():
    """Multiple behavior ACs are all demoted."""
    acs = [
        "behavior: first claim",
        "behavior: second claim",
        "behavior: third claim",
    ]
    result = reject_behavior_ac_for_verifier_extensions(acs, _VERIFIER_TARGET)
    assert result.is_verifier_extension is True
    assert len(result.demoted) == 3


def test_empty_acs_verifier_extension_returns_empty():
    """Empty AC list for a verifier-extension target returns empty filtered list without error."""
    result = reject_behavior_ac_for_verifier_extensions([], _VERIFIER_TARGET)
    assert result.filtered_acs == []
    assert result.demoted == []
    assert result.is_verifier_extension is True


def test_empty_acs_normal_feature_returns_empty():
    """Empty AC list for a normal feature returns empty filtered list without error."""
    result = reject_behavior_ac_for_verifier_extensions([], _NORMAL_TARGET)
    assert result.filtered_acs == []
    assert result.demoted == []
    assert result.is_verifier_extension is False


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_non_list_raises_value_error():
    """Non-list acceptance_criteria raises ValueError."""
    with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
        reject_behavior_ac_for_verifier_extensions("not a list", _VERIFIER_TARGET)


def test_none_raises_value_error():
    """None acceptance_criteria raises ValueError."""
    with pytest.raises(ValueError):
        reject_behavior_ac_for_verifier_extensions(None, _VERIFIER_TARGET)


def test_tuple_raises_value_error():
    """Tuple (not list) acceptance_criteria raises ValueError."""
    with pytest.raises(ValueError):
        reject_behavior_ac_for_verifier_extensions(("behavior: test",), _VERIFIER_TARGET)


# ---------------------------------------------------------------------------
# Feature ID handling
# ---------------------------------------------------------------------------


def test_feature_id_optional():
    """Omitting feature_id (default None) does not raise."""
    result = reject_behavior_ac_for_verifier_extensions(["behavior: x"], _VERIFIER_TARGET)
    assert result is not None


def test_feature_id_passed_through():
    """Explicit feature_id does not change the structural result."""
    result = reject_behavior_ac_for_verifier_extensions(
        ["behavior: x"], _VERIFIER_TARGET, feature_id="feat-123"
    )
    assert result.is_verifier_extension is True
    assert len(result.demoted) == 1


# ---------------------------------------------------------------------------
# VERIFIER_EXTENSION_MODULES constant
# ---------------------------------------------------------------------------


def test_verifier_extension_modules_is_non_empty_tuple():
    """VERIFIER_EXTENSION_MODULES is a non-empty tuple of non-empty strings."""
    assert isinstance(VERIFIER_EXTENSION_MODULES, tuple)
    assert len(VERIFIER_EXTENSION_MODULES) > 0
    for path in VERIFIER_EXTENSION_MODULES:
        assert isinstance(path, str) and path


def test_verifier_extension_modules_contains_enhanced_verification():
    """enhanced_verification.py is in VERIFIER_EXTENSION_MODULES."""
    assert any("enhanced_verification" in m for m in VERIFIER_EXTENSION_MODULES)
