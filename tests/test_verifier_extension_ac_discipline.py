"""Tests for bob.spec.verifier_extension_checker.reject_behavior_ac_for_verifier_extension.

Verifies that the AC discipline rule is enforced at spec-extraction time:
features whose primary diff target is a verifier-extension module must not
carry behavior ACs.
"""

from __future__ import annotations

import pytest

from bob.spec.verifier_extension_checker import (
    VERIFIER_EXTENSION_MODULES,
    ACFilterResult,
    DemotedAC,
    reject_behavior_ac_for_verifier_extension,
)

_VERIFIER_TARGET = "src/bob/enhanced_verification.py"
_NORMAL_TARGET = "src/bob/some_other_module.py"


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------


def test_module_exports_function():
    """reject_behavior_ac_for_verifier_extension is importable from the module."""
    assert callable(reject_behavior_ac_for_verifier_extension)


def test_module_exports_verifier_extension_modules():
    """VERIFIER_EXTENSION_MODULES is a non-empty tuple of strings."""
    assert isinstance(VERIFIER_EXTENSION_MODULES, tuple)
    assert len(VERIFIER_EXTENSION_MODULES) > 0


def test_module_exports_ac_filter_result():
    """ACFilterResult and DemotedAC are importable from the module."""
    assert ACFilterResult is not None
    assert DemotedAC is not None


# ---------------------------------------------------------------------------
# Normal feature — pass through
# ---------------------------------------------------------------------------


def test_normal_feature_passes_through():
    """Non-verifier-extension features pass through unchanged."""
    acs = ["behavior: the system MUST do X", "structural: file Y contains Z"]
    result = reject_behavior_ac_for_verifier_extension(acs, _NORMAL_TARGET)
    assert result.is_verifier_extension is False
    assert result.filtered_acs == acs
    assert result.demoted == []


def test_normal_feature_returns_ac_filter_result():
    """Return type is ACFilterResult for normal features."""
    result = reject_behavior_ac_for_verifier_extension([], _NORMAL_TARGET)
    assert isinstance(result, ACFilterResult)


# ---------------------------------------------------------------------------
# Verifier-extension feature — behavior ACs demoted
# ---------------------------------------------------------------------------


def test_verifier_extension_rejects_behavior_ac():
    """Behavior ACs are demoted when primary_diff_target is a verifier-extension module."""
    acs = ["behavior: output MUST contain X"]
    result = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
    assert result.is_verifier_extension is True
    assert len(result.demoted) == 1
    assert result.demoted[0].original == acs[0]
    assert "[SKIP" in result.filtered_acs[0]


def test_verifier_extension_keeps_structural_ac():
    """Structural ACs pass through unchanged for verifier-extension features."""
    acs = ["structural: src/bob/enhanced_verification.py contains function foo"]
    result = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
    assert result.is_verifier_extension is True
    assert result.filtered_acs == acs
    assert result.demoted == []


def test_verifier_extension_keeps_integration_ac():
    """Integration pytest ACs pass through unchanged for verifier-extension features."""
    acs = ["integration: pytest tests/test_foo.py::test_bar passes"]
    result = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
    assert result.is_verifier_extension is True
    assert result.filtered_acs == acs
    assert result.demoted == []


def test_verifier_extension_mixed_acs():
    """Only behavior ACs are demoted; structural/integration ACs pass through."""
    acs = [
        "behavior: output MUST contain X",
        "structural: file Y contains regex Z",
        "behavior: the system MUST do W",
        "pytest: tests/test_foo.py",
    ]
    result = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
    assert result.is_verifier_extension is True
    assert len(result.demoted) == 2
    assert len(result.filtered_acs) == 4
    assert result.filtered_acs[1] == acs[1]
    assert result.filtered_acs[3] == acs[3]
    assert "[SKIP" in result.filtered_acs[0]
    assert "[SKIP" in result.filtered_acs[2]


def test_demoted_record_contains_original_and_skip_note():
    """DemotedAC record has original and skip_note fields set correctly."""
    acs = ["behavior: something MUST happen"]
    result = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
    assert len(result.demoted) == 1
    demoted = result.demoted[0]
    assert demoted.original == acs[0]
    assert isinstance(demoted.skip_note, str)
    assert len(demoted.skip_note) > 0


def test_behavior_ac_case_insensitive():
    """BEHAVIOR: and Behavior: prefixes are both caught."""
    for prefix in ("BEHAVIOR:", "Behavior:", "behavior:"):
        acs = [f"{prefix} some AC text"]
        result = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
        assert len(result.demoted) == 1, f"Expected demotion for prefix {prefix!r}"


def test_feature_id_accepted():
    """feature_id kwarg is accepted without error."""
    result = reject_behavior_ac_for_verifier_extension(
        ["behavior: X MUST do Y"], _VERIFIER_TARGET, feature_id="test-feature-123"
    )
    assert result.is_verifier_extension is True


def test_feature_id_none_accepted():
    """feature_id=None (default) does not raise."""
    result = reject_behavior_ac_for_verifier_extension(
        ["behavior: X MUST do Y"], _VERIFIER_TARGET
    )
    assert result.is_verifier_extension is True


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_non_list_raises_value_error():
    """Passing a non-list raises ValueError."""
    with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
        reject_behavior_ac_for_verifier_extension("not a list", _VERIFIER_TARGET)


def test_none_raises_value_error():
    """Passing None raises ValueError."""
    with pytest.raises(ValueError):
        reject_behavior_ac_for_verifier_extension(None, _VERIFIER_TARGET)


def test_tuple_raises_value_error():
    """Passing a tuple raises ValueError."""
    with pytest.raises(ValueError):
        reject_behavior_ac_for_verifier_extension(("behavior: X",), _VERIFIER_TARGET)


# ---------------------------------------------------------------------------
# Integration with bob.spec_extractor
# ---------------------------------------------------------------------------


def test_integration_bob_spec_extractor_consistent():
    """reject_behavior_ac_for_verifier_extension is consistent with bob.spec_extractor."""
    from bob.spec_extractor import reject_behavior_ac_for_verifier_extension as extractor_fn

    acs = ["behavior: something MUST happen", "structural: file X contains Y"]
    result_checker = reject_behavior_ac_for_verifier_extension(acs, _VERIFIER_TARGET)
    result_extractor = extractor_fn(acs, _VERIFIER_TARGET)

    assert result_checker.is_verifier_extension == result_extractor.is_verifier_extension
    assert result_checker.filtered_acs == result_extractor.filtered_acs
    assert len(result_checker.demoted) == len(result_extractor.demoted)
