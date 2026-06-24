"""Tests for bob.verifier_extension_ac_enforcer.enforce_ac_discipline.

Verifies that behavior ACs are demoted for verifier-extension features and
normal features pass through unchanged.
"""

from __future__ import annotations

import logging

import pytest

from bob.verifier_extension_ac_enforcer import (
    VERIFIER_EXTENSION_MODULES,
    ACFilterResult,
    DemotedAC,
    enforce_ac_discipline,
)


def test_enforce_ac_discipline_demotes_behavior_ac():
    """Behavior ACs are demoted when the primary target is a verifier-extension module."""
    acs = [
        "structural: src/bob/enhanced_verification.py contains regex PATTERN",
        "behavior: when feature X runs, output MUST contain Y",
        "integration: pytest tests/test_verifier.py::test_check passes",
    ]
    result = enforce_ac_discipline(
        acs,
        "src/bob/enhanced_verification.py",
        feature_id="test-feature-abc",
    )

    assert isinstance(result, ACFilterResult)
    assert result.is_verifier_extension is True
    assert len(result.demoted) == 1
    assert isinstance(result.demoted[0], DemotedAC)
    assert result.demoted[0].original == "behavior: when feature X runs, output MUST contain Y"
    assert len(result.filtered_acs) == 3
    assert "[SKIP: verifier-extension AC discipline]" in result.filtered_acs[1]
    assert result.filtered_acs[0] == acs[0]
    assert result.filtered_acs[2] == acs[2]


def test_enforce_ac_discipline_non_verifier_extension_passes_unchanged():
    """Non-verifier-extension features pass all ACs through unchanged."""
    acs = [
        "structural: some/module.py has function foo",
        "behavior: when input is X, output MUST be Y",
        "integration: pytest tests/test_foo.py::test_bar passes",
    ]
    result = enforce_ac_discipline(
        acs,
        "src/bob/some_other_module.py",
        feature_id="test-normal",
    )

    assert result.is_verifier_extension is False
    assert result.demoted == []
    assert result.filtered_acs == acs


def test_enforce_ac_discipline_multiple_behavior_acs():
    """Multiple behavior ACs are all demoted for a verifier-extension feature."""
    acs = [
        "behavior: first behavior",
        "behavior: second behavior",
        "structural: file has function foo",
    ]
    result = enforce_ac_discipline(
        acs,
        "src/bob/verification/verifier.py",
        feature_id="test-multi-behavior",
    )

    assert result.is_verifier_extension is True
    assert len(result.demoted) == 2
    assert len(result.filtered_acs) == 3
    for i in range(2):
        assert "[SKIP: verifier-extension AC discipline]" in result.filtered_acs[i]


def test_enforce_ac_discipline_all_modules_trigger_rule():
    """Every module in VERIFIER_EXTENSION_MODULES triggers the discipline rule."""
    acs = ["behavior: some behavior AC"]
    for module_path in VERIFIER_EXTENSION_MODULES:
        result = enforce_ac_discipline(acs, module_path, feature_id="test-modules")
        assert result.is_verifier_extension is True, f"Expected {module_path!r} to trigger rule"
        assert len(result.demoted) == 1


def test_enforce_ac_discipline_skip_note_contains_remediation():
    """The skip note tells the developer to use structural or integration form."""
    acs = ["behavior: output must contain token X"]
    result = enforce_ac_discipline(
        acs,
        "src/bob/enhanced_verification.py",
        feature_id="test-hint",
    )

    skip_note = result.demoted[0].skip_note
    assert "structural" in skip_note or "integration" in skip_note


def test_enforce_ac_discipline_warning_logged_per_demoted_ac():
    """One WARNING is logged for each demoted behavior AC."""
    acs = ["behavior: first", "behavior: second"]
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    logger = logging.getLogger("bob.spec_quality.spec_extractor")
    logger.addHandler(handler)
    try:
        result = enforce_ac_discipline(
            acs,
            "src/bob/enhanced_verification.py",
            feature_id="test-warn",
        )
    finally:
        logger.removeHandler(handler)

    assert result.is_verifier_extension is True
    warnings = [r for r in records if r.levelno == logging.WARNING]
    assert len(warnings) == 2


def test_enforce_ac_discipline_returns_ac_filter_result():
    """Return type is ACFilterResult with expected fields."""
    result = enforce_ac_discipline([], "src/bob/enhanced_verification.py")
    assert hasattr(result, "filtered_acs")
    assert hasattr(result, "demoted")
    assert hasattr(result, "is_verifier_extension")


def test_enforce_ac_discipline_integration_with_spec_extractor():
    """enforce_ac_discipline delegates to spec_extractor and is consistent with it."""
    from bob.spec_quality.spec_extractor import filter_behavior_acs_for_verifier_extension

    acs = ["behavior: test behavior", "structural: test structural"]
    target = "src/bob/enhanced_verification.py"

    result_enforcer = enforce_ac_discipline(acs, target, feature_id="test-integration")
    result_extractor = filter_behavior_acs_for_verifier_extension(acs, target, feature_id="test-integration")

    assert result_enforcer.filtered_acs == result_extractor.filtered_acs
    assert result_enforcer.is_verifier_extension == result_extractor.is_verifier_extension
    assert len(result_enforcer.demoted) == len(result_extractor.demoted)
