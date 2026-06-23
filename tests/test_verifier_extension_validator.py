"""Tests for bob3.verifier_extension_validator.validate_ac_for_extension.

Covers the main entry point that enforces AC discipline for verifier-extension
features: behavior ACs are demoted; structural/pytest ACs pass through.
"""

from __future__ import annotations

import pytest

from bob3.verifier_extension_validator import (
    VERIFIER_EXTENSION_MODULES,
    ACFilterResult,
    DemotedAC,
    validate_ac_for_extension,
)

_VERIFIER_TARGET = "src/bob3/enhanced_verification.py"
_NORMAL_TARGET = "src/bob3/some_unrelated_module.py"


# ---------------------------------------------------------------------------
# Basic passthrough (non-verifier-extension)
# ---------------------------------------------------------------------------


def test_normal_feature_passes_through_unchanged():
    """ACs for a non-verifier-extension target are returned unchanged."""
    acs = ["behavior: output must contain X", "structural: file Y exists"]
    result = validate_ac_for_extension(acs, _NORMAL_TARGET)
    assert result.filtered_acs == acs
    assert result.demoted == []
    assert result.is_verifier_extension is False


def test_normal_feature_returns_ac_filter_result():
    """Return type is ACFilterResult."""
    result = validate_ac_for_extension([], _NORMAL_TARGET)
    assert isinstance(result, ACFilterResult)


# ---------------------------------------------------------------------------
# Verifier-extension: behavior ACs get demoted
# ---------------------------------------------------------------------------


def test_behavior_ac_demoted_for_verifier_extension():
    """behavior: ACs for a verifier-extension target are demoted."""
    acs = ["behavior: output MUST contain X"]
    result = validate_ac_for_extension(acs, _VERIFIER_TARGET)
    assert result.is_verifier_extension is True
    assert len(result.demoted) == 1
    assert isinstance(result.demoted[0], DemotedAC)
    assert result.demoted[0].original == acs[0]
    assert "[SKIP" in result.filtered_acs[0]


def test_multiple_behavior_acs_all_demoted():
    """Multiple behavior: ACs are all demoted."""
    acs = [
        "behavior: output MUST contain X",
        "behavior: side-effect Y must occur",
        "structural: file Z contains regex W",
    ]
    result = validate_ac_for_extension(acs, _VERIFIER_TARGET)
    assert len(result.demoted) == 2
    assert len(result.filtered_acs) == 3
    assert result.filtered_acs[2] == acs[2]


def test_structural_ac_passes_through_for_verifier_extension():
    """structural: ACs for a verifier-extension target are NOT demoted."""
    acs = ["structural: src/bob3/enhanced_verification.py contains function foo"]
    result = validate_ac_for_extension(acs, _VERIFIER_TARGET)
    assert result.filtered_acs == acs
    assert result.demoted == []
    assert result.is_verifier_extension is True


def test_pytest_ac_passes_through_for_verifier_extension():
    """pytest: ACs for a verifier-extension target are NOT demoted."""
    acs = ["pytest: tests/test_enhanced_verification.py"]
    result = validate_ac_for_extension(acs, _VERIFIER_TARGET)
    assert result.filtered_acs == acs
    assert result.demoted == []


def test_integration_ac_passes_through_for_verifier_extension():
    """integration: ACs for a verifier-extension target are NOT demoted."""
    acs = ["integration: pytest tests/test_foo.py::test_bar passes"]
    result = validate_ac_for_extension(acs, _VERIFIER_TARGET)
    assert result.filtered_acs == acs
    assert result.demoted == []


# ---------------------------------------------------------------------------
# Case-insensitivity
# ---------------------------------------------------------------------------


def test_behavior_ac_case_insensitive():
    """'BEHAVIOR:' and 'Behavior:' prefixes are demoted (case-insensitive)."""
    for prefix in ("BEHAVIOR:", "Behavior:", "behavior:"):
        acs = [f"{prefix} some criterion"]
        result = validate_ac_for_extension(acs, _VERIFIER_TARGET)
        assert len(result.demoted) == 1, f"Expected demotion for prefix {prefix!r}"


# ---------------------------------------------------------------------------
# Optional feature_id parameter
# ---------------------------------------------------------------------------


def test_feature_id_none_does_not_raise():
    """Omitting feature_id (default None) does not raise."""
    result = validate_ac_for_extension(["behavior: test"], _VERIFIER_TARGET)
    assert result.is_verifier_extension is True


def test_feature_id_provided_does_not_raise():
    """Providing a feature_id string does not raise."""
    result = validate_ac_for_extension(
        ["behavior: test"], _VERIFIER_TARGET, feature_id="feat-abc"
    )
    assert result.is_verifier_extension is True


# ---------------------------------------------------------------------------
# VERIFIER_EXTENSION_MODULES constant
# ---------------------------------------------------------------------------


def test_verifier_extension_modules_is_non_empty_tuple():
    """VERIFIER_EXTENSION_MODULES is a non-empty tuple of strings."""
    assert isinstance(VERIFIER_EXTENSION_MODULES, tuple)
    assert len(VERIFIER_EXTENSION_MODULES) > 0
    for path in VERIFIER_EXTENSION_MODULES:
        assert isinstance(path, str)


def test_enhanced_verification_in_verifier_extension_modules():
    """src/bob3/enhanced_verification.py is in VERIFIER_EXTENSION_MODULES."""
    assert any(
        "enhanced_verification" in mod for mod in VERIFIER_EXTENSION_MODULES
    )


# ---------------------------------------------------------------------------
# Error path: invalid input
# ---------------------------------------------------------------------------


def test_non_list_raises_value_error():
    """Passing a non-list raises ValueError."""
    with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
        validate_ac_for_extension("not a list", _VERIFIER_TARGET)


def test_none_raises_value_error():
    """Passing None raises ValueError."""
    with pytest.raises(ValueError):
        validate_ac_for_extension(None, _VERIFIER_TARGET)


def test_tuple_raises_value_error():
    """Passing a tuple (not a list) raises ValueError."""
    with pytest.raises(ValueError):
        validate_ac_for_extension(("behavior: test",), _VERIFIER_TARGET)


def test_error_message_includes_actual_type():
    """ValueError message includes the name of the type passed."""
    with pytest.raises(ValueError, match="str"):
        validate_ac_for_extension("bad", _VERIFIER_TARGET)


# ---------------------------------------------------------------------------
# Integration: spec_extractor ACFilterResult fields
# ---------------------------------------------------------------------------


def test_demoted_ac_has_original_and_skip_note():
    """DemotedAC.original and .skip_note are both non-empty strings."""
    acs = ["behavior: this should be demoted"]
    result = validate_ac_for_extension(acs, _VERIFIER_TARGET)
    assert len(result.demoted) == 1
    demoted = result.demoted[0]
    assert demoted.original == acs[0]
    assert isinstance(demoted.skip_note, str)
    assert len(demoted.skip_note) > 0


def test_skip_note_suggests_structural_form():
    """The skip note mentions 'structural' as an alternative."""
    acs = ["behavior: check something"]
    result = validate_ac_for_extension(acs, _VERIFIER_TARGET)
    assert "structural" in result.demoted[0].skip_note.lower()
