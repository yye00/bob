"""Tests for ac_discipline_rule_verifier_extension_features_must_express module.

Verifies that verifier-extension features have behavior ACs demoted, while
normal features pass through unchanged (F-2b0d6c5b).
"""

from __future__ import annotations

import logging

from bob.ac_discipline_rule_verifier_extension_features_must_express import (
    VERIFIER_EXTENSION_MODULES,
    ac_discipline_rule_verifier_extension_features_must_express,
)


def test_ac_discipline_rule_verifier_extension_features_must_express():
    """Primary AC guard: behavior ACs are demoted for verifier-extension features."""
    acs = [
        "structural: src/bob/enhanced_verification.py contains regex PATTERN",
        "behavior: when feature X is run, output MUST contain Y",
        "integration: pytest tests/test_verifier.py::test_check passes",
    ]
    result = ac_discipline_rule_verifier_extension_features_must_express(
        acs,
        "src/bob/enhanced_verification.py",
        feature_id="test-feature-2b0d6c5b",
    )

    assert result.is_verifier_extension is True
    assert len(result.demoted) == 1
    assert result.demoted[0].original == "behavior: when feature X is run, output MUST contain Y"
    assert len(result.filtered_acs) == 3
    assert "[SKIP: verifier-extension AC discipline]" in result.filtered_acs[1]
    assert "behavior: when feature X is run" in result.filtered_acs[1]
    assert result.filtered_acs[0] == acs[0]
    assert result.filtered_acs[2] == acs[2]


def test_normal_feature_passes_unchanged():
    """Non-verifier-extension features: all ACs including behavior ones pass through unchanged."""
    acs = [
        "structural: some/other/module.py has function foo",
        "behavior: when input is X, output MUST be Y",
        "integration: pytest tests/test_other.py::test_baz passes",
    ]
    result = ac_discipline_rule_verifier_extension_features_must_express(
        acs,
        "src/bob/some/other/module.py",
        feature_id="test-feature-normal",
    )

    assert result.is_verifier_extension is False
    assert result.demoted == []
    assert result.filtered_acs == acs


def test_warning_logged_for_each_demoted_ac():
    """A WARNING is emitted per demoted behavior AC."""
    acs = [
        "behavior: first demoted AC",
        "behavior: second demoted AC",
        "structural: src/bob/enhanced_verification.py has function check",
    ]
    log_records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            log_records.append(record)

    handler = _Capture()
    logger = logging.getLogger("bob.spec_quality.spec_extractor")
    logger.addHandler(handler)
    try:
        result = ac_discipline_rule_verifier_extension_features_must_express(
            acs,
            "src/bob/enhanced_verification.py",
            feature_id="test-feature-warn",
        )
    finally:
        logger.removeHandler(handler)

    assert result.is_verifier_extension is True
    assert len(result.demoted) == 2
    warnings = [r for r in log_records if r.levelno == logging.WARNING]
    assert len(warnings) == 2
    for record in warnings:
        msg = record.getMessage()
        assert "AC discipline" in msg
        assert "behavior AC demoted" in msg


def test_empty_acs_for_verifier_extension():
    """Empty AC list for a verifier-extension feature returns empty filtered list."""
    result = ac_discipline_rule_verifier_extension_features_must_express(
        [],
        "src/bob/enhanced_verification.py",
        feature_id="test-feature-empty",
    )

    assert result.is_verifier_extension is True
    assert result.filtered_acs == []
    assert result.demoted == []


def test_all_verifier_extension_modules_are_detected():
    """Every module in VERIFIER_EXTENSION_MODULES triggers the discipline rule."""
    acs = ["behavior: some behavior"]
    for module_path in VERIFIER_EXTENSION_MODULES:
        result = ac_discipline_rule_verifier_extension_features_must_express(
            acs,
            module_path,
            feature_id="test-feature-modules",
        )
        assert result.is_verifier_extension is True, f"Expected {module_path!r} to trigger discipline"
        assert len(result.demoted) == 1


def test_skip_note_contains_remediation_hint():
    """Demoted AC skip note suggests structural or integration pytest form."""
    acs = ["behavior: output must contain token X"]
    result = ac_discipline_rule_verifier_extension_features_must_express(
        acs,
        "src/bob/enhanced_verification.py",
        feature_id="test-feature-hint",
    )

    assert result.is_verifier_extension is True
    skip_note = result.demoted[0].skip_note
    assert "structural" in skip_note or "integration" in skip_note
