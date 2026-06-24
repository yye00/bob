"""Tests for bob.linter.smella_22 — the full 22-detector linter entry point.

Covers detect_all_smells and filter_by_severity for the Femmer/Smella +
2025-LLM-extension catalogue (F-R7-410 extension).
"""

from __future__ import annotations

import pytest

from bob.linter.smella_22 import (
    BLOCKING_SMELLS,
    SMELL_BY_ID,
    SMELL_CATALOG,
    SPACY_SMELLS,
    SmellDefinition,
    SmellFinding,
    SmellSeverity,
    Severity,
    blocks_plan_create,
    detect_all_smells,
    detector_count,
    filter_by_severity,
    is_blocking,
    severity_of,
    spacy_backed_detectors,
)


# ---------------------------------------------------------------------------
# detect_all_smells — basic contract
# ---------------------------------------------------------------------------


def test_detect_all_smells_returns_list_for_clean_ac():
    findings = detect_all_smells("pytest: tests/test_foo.py")
    assert isinstance(findings, list)
    assert findings == []


def test_detect_all_smells_detects_subjective_adjective():
    findings = detect_all_smells("The system shall be fast and simple.")
    assert len(findings) > 0
    assert any(f.blocks_plan for f in findings)


def test_detect_all_smells_findings_have_required_attrs():
    findings = detect_all_smells("The system shall be fast.")
    assert len(findings) > 0
    for f in findings:
        assert hasattr(f, "smell_id")
        assert hasattr(f, "severity")
        assert hasattr(f, "blocks_plan")
        assert hasattr(f, "detail")
        assert f.severity in {"E", "W", "I"}


def test_detect_all_smells_empty_string_returns_empty():
    findings = detect_all_smells("")
    assert findings == []


def test_detect_all_smells_whitespace_no_crash():
    findings = detect_all_smells("   \n  ")
    assert isinstance(findings, list)


def test_detect_all_smells_raises_on_non_str():
    with pytest.raises(ValueError, match="str"):
        detect_all_smells(42)  # type: ignore[arg-type]


def test_detect_all_smells_raises_on_none():
    with pytest.raises((ValueError, TypeError)):
        detect_all_smells(None)  # type: ignore[arg-type]


def test_detect_all_smells_peer_criteria_no_crash():
    findings = detect_all_smells(
        "behavior: X must happen",
        peer_criteria=["pytest: tests/test_foo.py"],
    )
    assert isinstance(findings, list)


def test_detect_all_smells_known_feature_ids_no_crash():
    findings = detect_all_smells(
        "F-R7-100 must pass",
        known_feature_ids=frozenset(["F-R7-100"]),
    )
    assert isinstance(findings, list)


# ---------------------------------------------------------------------------
# filter_by_severity — basic contract
# ---------------------------------------------------------------------------


def test_filter_by_severity_e_returns_only_errors():
    findings = detect_all_smells("The system shall be fast and simple.")
    errors = filter_by_severity(findings, "E")
    assert all(f.severity == "E" for f in errors)


def test_filter_by_severity_w_returns_only_warnings():
    findings = detect_all_smells("The response time shall be better than before.")
    warnings = filter_by_severity(findings, "W")
    assert all(f.severity == "W" for f in warnings)


def test_filter_by_severity_i_returns_only_info():
    findings = detect_all_smells("The system shall be fast.")
    info = filter_by_severity(findings, "I")
    assert all(f.severity == "I" for f in info)


def test_filter_by_severity_empty_findings_returns_empty():
    result = filter_by_severity([], "E")
    assert result == []


def test_filter_by_severity_invalid_level_raises():
    with pytest.raises(ValueError, match="Invalid severity"):
        filter_by_severity([], "X")


# ---------------------------------------------------------------------------
# Catalogue size and integrity
# ---------------------------------------------------------------------------


def test_detector_count_is_22():
    assert detector_count() == 22


def test_smell_catalog_has_22_entries():
    assert len(SMELL_CATALOG) == 22


def test_smell_catalog_ids_unique():
    ids = [s.id for s in SMELL_CATALOG]
    assert len(ids) == len(set(ids))


def test_smell_catalog_severities_valid():
    valid = {"E", "W", "I"}
    for smell in SMELL_CATALOG:
        assert smell.severity in valid


def test_spacy_backed_detectors_returns_seven():
    backed = spacy_backed_detectors()
    assert len(backed) == 7


def test_blocking_smells_all_e_severity():
    for smell_id in BLOCKING_SMELLS:
        defn = SMELL_BY_ID[smell_id]
        assert defn.severity == "E"


def test_smell_by_id_lookup():
    for smell in SMELL_CATALOG:
        assert SMELL_BY_ID[smell.id] is smell


# ---------------------------------------------------------------------------
# blocks_plan_create integration
# ---------------------------------------------------------------------------


def test_blocks_plan_create_true_for_e_findings():
    findings = detect_all_smells("The system shall be fast and simple.")
    assert blocks_plan_create(findings) is True


def test_blocks_plan_create_false_for_clean_ac():
    findings = detect_all_smells("pytest: tests/test_foo.py")
    assert blocks_plan_create(findings) is False


def test_blocks_plan_create_false_for_empty():
    assert blocks_plan_create([]) is False
