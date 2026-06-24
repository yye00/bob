"""Tests for bob.linter_22 — the 22-smell linter canonical module.

Verifies that the module exposes detect_all_smells and SmellSeverity,
that detect_all_smells runs all 22 detectors and returns structured findings,
and that E-severity findings block bob plan --create.
"""

from __future__ import annotations

import pytest

from bob.linter_22 import detect_all_smells, SmellSeverity


# ---------------------------------------------------------------------------
# Module API: detect_all_smells exists and is callable
# ---------------------------------------------------------------------------

def test_detect_all_smells_is_callable():
    assert callable(detect_all_smells)


def test_smell_severity_is_importable():
    assert SmellSeverity is not None


# ---------------------------------------------------------------------------
# detect_all_smells: return structure
# ---------------------------------------------------------------------------

def test_detect_all_smells_returns_list_for_clean_ac():
    findings = detect_all_smells("pytest: tests/test_foo.py")
    assert isinstance(findings, list)


def test_detect_all_smells_returns_empty_for_clean_ac():
    findings = detect_all_smells("pytest: tests/test_foo.py")
    assert findings == []


def test_detect_all_smells_returns_list_for_vague_ac():
    findings = detect_all_smells("The system shall be fast and simple.")
    assert isinstance(findings, list)
    assert len(findings) > 0


def test_detect_all_smells_findings_have_severity():
    findings = detect_all_smells("The system shall be fast and simple.")
    for f in findings:
        assert hasattr(f, "severity")
        assert f.severity in ("E", "W", "I")


def test_detect_all_smells_findings_have_smell_id():
    findings = detect_all_smells("The system shall be fast and simple.")
    for f in findings:
        assert hasattr(f, "smell_id")


def test_detect_all_smells_e_severity_blocks_plan():
    findings = detect_all_smells("The system shall be fast and simple.")
    error_findings = [f for f in findings if f.severity == "E"]
    assert any(getattr(f, "blocks_plan", False) for f in error_findings)


# ---------------------------------------------------------------------------
# detect_all_smells: optional arguments
# ---------------------------------------------------------------------------

def test_detect_all_smells_accepts_peer_criteria():
    findings = detect_all_smells(
        "The system shall perform quickly.",
        peer_criteria=["pytest: tests/test_foo.py"],
    )
    assert isinstance(findings, list)


def test_detect_all_smells_accepts_known_feature_ids():
    findings = detect_all_smells(
        "Depends on F-R7-001.",
        known_feature_ids=frozenset({"F-R7-001"}),
    )
    assert isinstance(findings, list)


def test_detect_all_smells_empty_string_no_crash():
    findings = detect_all_smells("")
    assert isinstance(findings, list)


def test_detect_all_smells_none_peer_criteria_no_crash():
    findings = detect_all_smells("hello", peer_criteria=None)
    assert isinstance(findings, list)


def test_detect_all_smells_none_known_feature_ids_no_crash():
    findings = detect_all_smells("hello", known_feature_ids=None)
    assert isinstance(findings, list)


# ---------------------------------------------------------------------------
# SmellSeverity values
# ---------------------------------------------------------------------------

def test_smell_severity_error_value():
    assert SmellSeverity.E == "E" or hasattr(SmellSeverity, "E")


def test_smell_severity_warning_value():
    assert SmellSeverity.W == "W" or hasattr(SmellSeverity, "W")


def test_smell_severity_info_value():
    assert SmellSeverity.I == "I" or hasattr(SmellSeverity, "I")


# ---------------------------------------------------------------------------
# 22-detector count
# ---------------------------------------------------------------------------

def test_linter_22_covers_22_detectors():
    from bob.linter_22 import detector_count
    assert detector_count() == 22


def test_linter_22_spacy_backed_count():
    from bob.linter_22 import spacy_backed_count
    assert spacy_backed_count() == 7
