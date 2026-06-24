"""Integration tests for bob.verifier.spec_extractor.

Tests the reject_behavior_acs_for_verifier_extensions function:
verifier-extension features must have behavior ACs rejected, while
normal features pass through unchanged.
"""

from __future__ import annotations

import logging

import pytest

from bob.verifier.spec_extractor import (
    VERIFIER_EXTENSION_MODULES,
    ACFilterResult,
    DemotedAC,
    reject_behavior_acs_for_verifier_extensions,
)

_VERIFIER_TARGET = "src/bob/enhanced_verification.py"
_NORMAL_TARGET = "src/bob/unrelated_module.py"


def test_behavior_ac_rejected_for_verifier_extension():
    """behavior ACs are demoted when primary_diff_target is a verifier-extension module."""
    acs = [
        "structural: src/bob/enhanced_verification.py contains function foo",
        "behavior: when condition Y, output MUST be Z",
        "integration: pytest tests/test_foo.py::test_bar passes",
    ]
    result = reject_behavior_acs_for_verifier_extensions(
        acs, _VERIFIER_TARGET, feature_id="test-001"
    )

    assert isinstance(result, ACFilterResult)
    assert result.is_verifier_extension is True
    assert len(result.demoted) == 1
    assert result.demoted[0].original == "behavior: when condition Y, output MUST be Z"
    assert len(result.filtered_acs) == 3
    assert "[SKIP" in result.filtered_acs[1]


def test_behavior_ac_kept_for_normal_feature():
    """behavior ACs pass through unchanged for non-verifier-extension features."""
    acs = [
        "structural: some/module.py has function foo",
        "behavior: when input is X, output MUST be Y",
    ]
    result = reject_behavior_acs_for_verifier_extensions(
        acs, _NORMAL_TARGET, feature_id="test-002"
    )

    assert result.is_verifier_extension is False
    assert result.demoted == []
    assert result.filtered_acs == acs


def test_non_list_raises_value_error():
    """Passing a non-list for acceptance_criteria raises ValueError."""
    with pytest.raises(ValueError, match="acceptance_criteria must be a list"):
        reject_behavior_acs_for_verifier_extensions("not a list", _VERIFIER_TARGET)


def test_none_raises_value_error():
    """Passing None raises ValueError."""
    with pytest.raises(ValueError):
        reject_behavior_acs_for_verifier_extensions(None, _VERIFIER_TARGET)


def test_empty_acs_verifier_extension_returns_empty():
    """Empty AC list for verifier-extension target returns empty filtered list."""
    result = reject_behavior_acs_for_verifier_extensions([], _VERIFIER_TARGET)
    assert result.filtered_acs == []
    assert result.demoted == []
    assert result.is_verifier_extension is True


def test_empty_acs_normal_feature_returns_empty():
    """Empty AC list for normal feature returns empty filtered list."""
    result = reject_behavior_acs_for_verifier_extensions([], _NORMAL_TARGET)
    assert result.filtered_acs == []
    assert result.demoted == []
    assert result.is_verifier_extension is False


def test_empty_primary_diff_target_treated_as_normal():
    """Empty string primary_diff_target is treated as non-verifier-extension."""
    acs = ["behavior: some behavior"]
    result = reject_behavior_acs_for_verifier_extensions(acs, "")
    assert result.is_verifier_extension is False
    assert result.filtered_acs == acs


def test_warning_logged_for_demoted_acs(caplog):
    """A WARNING is emitted for each demoted behavior AC."""
    acs = ["behavior: first", "behavior: second"]
    with caplog.at_level(logging.WARNING, logger="bob.verifier.spec_extractor"):
        result = reject_behavior_acs_for_verifier_extensions(
            acs, _VERIFIER_TARGET, feature_id="test-warn"
        )
    assert result.is_verifier_extension is True
    assert len(result.demoted) == 2
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) >= 1
    assert any("AC discipline" in r.getMessage() for r in warnings)


def test_multiple_behavior_acs_all_demoted():
    """All behavior ACs are demoted for a verifier-extension feature."""
    acs = [
        "behavior: first behavior",
        "structural: file contains pattern",
        "behavior: second behavior",
    ]
    result = reject_behavior_acs_for_verifier_extensions(acs, _VERIFIER_TARGET)
    assert len(result.demoted) == 2
    assert result.filtered_acs[1] == acs[1]
    assert "[SKIP" in result.filtered_acs[0]
    assert "[SKIP" in result.filtered_acs[2]


def test_case_insensitive_behavior_prefix():
    """'BEHAVIOR:' and 'Behavior:' prefixes are caught."""
    for prefix in ("BEHAVIOR: upper", "Behavior: mixed"):
        result = reject_behavior_acs_for_verifier_extensions([prefix], _VERIFIER_TARGET)
        assert len(result.demoted) == 1, f"Expected demotion for: {prefix!r}"


def test_all_verifier_extension_modules_trigger_rule():
    """Every module in VERIFIER_EXTENSION_MODULES triggers the discipline rule."""
    acs = ["behavior: some behavior"]
    for module_path in VERIFIER_EXTENSION_MODULES:
        result = reject_behavior_acs_for_verifier_extensions(acs, module_path)
        assert result.is_verifier_extension is True, f"{module_path!r} should trigger rule"
        assert len(result.demoted) == 1


def test_structural_and_integration_acs_pass_through():
    """Structural and integration ACs pass through unchanged for verifier-extension."""
    acs = [
        "structural: file X contains regex Y",
        "integration: pytest tests/test_foo.py::test_bar passes",
        "pytest: tests/test_baz.py",
    ]
    result = reject_behavior_acs_for_verifier_extensions(acs, _VERIFIER_TARGET)
    assert result.filtered_acs == acs
    assert result.demoted == []
    assert result.is_verifier_extension is True


def test_skip_note_suggests_remediation():
    """Demoted AC skip note suggests structural or integration pytest form."""
    acs = ["behavior: output must contain token X"]
    result = reject_behavior_acs_for_verifier_extensions(acs, _VERIFIER_TARGET)
    skip_note = result.demoted[0].skip_note
    assert "structural" in skip_note or "integration" in skip_note


def test_demoted_ac_contains_original():
    """DemotedAC.original preserves the verbatim AC string."""
    ac = "behavior: when X happens, Y MUST occur"
    result = reject_behavior_acs_for_verifier_extensions([ac], _VERIFIER_TARGET)
    assert result.demoted[0].original == ac


def test_verifier_extension_modules_constant_is_non_empty():
    """VERIFIER_EXTENSION_MODULES is a non-empty tuple of strings."""
    assert isinstance(VERIFIER_EXTENSION_MODULES, tuple)
    assert len(VERIFIER_EXTENSION_MODULES) > 0
    for path in VERIFIER_EXTENSION_MODULES:
        assert isinstance(path, str) and len(path) > 0


def test_no_feature_id_does_not_raise():
    """Calling without feature_id does not raise."""
    result = reject_behavior_acs_for_verifier_extensions(
        ["behavior: test"], _VERIFIER_TARGET
    )
    assert result.is_verifier_extension is True
