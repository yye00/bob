"""Integration tests for the AC discipline rule (F-1d5b0d3a).

Tests the filter_behavior_acs_for_verifier_extension function in
spec_extractor.py: verifier-extension features must not carry forward
behavior ACs; normal features must pass behavior ACs unchanged.
"""

from __future__ import annotations

import logging

from bob.spec_quality.spec_extractor import filter_behavior_acs_for_verifier_extension


def test_behavior_ac_rejected_for_verifier_extension():
    """behavior ACs are demoted when primary_diff_target is a verifier-extension module."""
    acs = [
        "structural: src/bob/enhanced_verification.py contains regex X",
        "behavior: when condition Y, output MUST be Z",
        "integration: pytest tests/test_foo.py::test_bar passes",
    ]
    result = filter_behavior_acs_for_verifier_extension(
        acs,
        "src/bob/enhanced_verification.py",
        feature_id="test-feature-001",
    )

    assert result.is_verifier_extension is True
    assert len(result.demoted) == 1
    assert result.demoted[0].original == "behavior: when condition Y, output MUST be Z"
    assert len(result.filtered_acs) == 3
    demoted_text = result.filtered_acs[1]
    assert "[SKIP: verifier-extension AC discipline]" in demoted_text
    assert "behavior: when condition Y" in demoted_text


def test_behavior_ac_kept_for_normal_feature():
    """behavior ACs are carried forward unchanged for non-verifier-extension features."""
    acs = [
        "structural: some/other/module.py has function foo",
        "behavior: when input is X, output MUST be Y",
        "integration: pytest tests/test_other.py::test_baz passes",
    ]
    result = filter_behavior_acs_for_verifier_extension(
        acs,
        "src/bob/some/other/module.py",
        feature_id="test-feature-002",
    )

    assert result.is_verifier_extension is False
    assert result.demoted == []
    assert result.filtered_acs == acs


def test_warning_log_emitted():
    """A WARNING is emitted for each demoted behavior AC."""
    acs = [
        "behavior: first behavior AC",
        "behavior: second behavior AC",
    ]

    log_records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            log_records.append(record)

    handler = _Capture()
    logger = logging.getLogger("bob.spec_quality.spec_extractor")
    logger.addHandler(handler)
    try:
        result = filter_behavior_acs_for_verifier_extension(
            acs,
            "src/bob/enhanced_verification.py",
            feature_id="test-feature-003",
        )
    finally:
        logger.removeHandler(handler)

    assert result.is_verifier_extension is True
    assert len(result.demoted) == 2
    warning_records = [r for r in log_records if r.levelno == logging.WARNING]
    assert len(warning_records) == 2
    for record in warning_records:
        assert "AC discipline" in record.getMessage()
        assert "behavior AC demoted" in record.getMessage()
