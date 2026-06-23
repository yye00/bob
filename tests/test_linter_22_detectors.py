"""Tests for bob3.linter_22_detectors — the 22-smell linter module (F-R7-410)."""

from __future__ import annotations

import pytest

from bob3.linter_22_detectors import (
    SMELL_BY_ID,
    SMELL_CATALOG,
    SmellFinding,
    blocks_plan_create,
    detect_smells,
    get_severity,
)


class TestDetectSmellsBasicContract:
    def test_returns_list(self):
        result = detect_smells("pytest: tests/test_foo.py")
        assert isinstance(result, list)

    def test_empty_string_returns_empty_list(self):
        assert detect_smells("") == []

    def test_clean_ac_returns_empty_list(self):
        findings = detect_smells("pytest: tests/test_foo.py")
        assert blocks_plan_create(findings) is False

    def test_subjective_adjective_triggers_e_severity(self):
        findings = detect_smells("The system shall be fast and simple.")
        assert any(f.blocks_plan for f in findings)

    def test_findings_are_smell_finding_instances(self):
        findings = detect_smells("The system shall be fast.")
        for f in findings:
            assert isinstance(f, SmellFinding)

    def test_finding_has_smell_id(self):
        findings = detect_smells("The system shall be fast.")
        assert all(f.smell_id for f in findings)

    def test_finding_severity_is_e_w_or_i(self):
        findings = detect_smells("The system shall be fast.")
        for f in findings:
            assert f.severity in ("E", "W", "I")

    def test_peer_criteria_none_accepted(self):
        result = detect_smells("pytest: tests/test_foo.py", peer_criteria=None)
        assert isinstance(result, list)

    def test_peer_criteria_list_accepted(self):
        result = detect_smells(
            "pytest: tests/test_foo.py",
            peer_criteria=["File exists: src/bob3/foo.py"],
        )
        assert isinstance(result, list)

    def test_known_feature_ids_none_accepted(self):
        result = detect_smells("pytest: tests/test_foo.py", known_feature_ids=None)
        assert isinstance(result, list)

    def test_known_feature_ids_frozenset_accepted(self):
        result = detect_smells(
            "pytest: tests/test_foo.py",
            known_feature_ids=frozenset(["feat-001"]),
        )
        assert isinstance(result, list)


class TestDetectSmellsErrorHandling:
    def test_non_string_raises_type_error(self):
        with pytest.raises(TypeError):
            detect_smells(object())  # type: ignore[arg-type]

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            detect_smells(None)  # type: ignore[arg-type]

    def test_integer_raises_type_error(self):
        with pytest.raises(TypeError):
            detect_smells(42)  # type: ignore[arg-type]


class TestGetSeverity:
    def test_s01_is_error(self):
        assert get_severity("S01") == "E"

    def test_s02_is_warning(self):
        assert get_severity("S02") == "W"

    def test_all_22_smells_return_valid_severity(self):
        for i in range(1, 23):
            sid = f"S{i:02d}"
            sev = get_severity(sid)
            assert sev in ("E", "W", "I"), f"{sid} has invalid severity {sev!r}"

    def test_unknown_smell_id_raises_key_error(self):
        with pytest.raises(KeyError):
            get_severity("S99")

    def test_empty_string_raises_key_error(self):
        with pytest.raises(KeyError):
            get_severity("")


class TestCatalogueIntegrity:
    def test_exactly_22_smells(self):
        assert len(SMELL_CATALOG) == 22

    def test_smell_by_id_has_22_entries(self):
        assert len(SMELL_BY_ID) == 22

    def test_all_ids_s01_to_s22(self):
        expected = {f"S{i:02d}" for i in range(1, 23)}
        assert {s.id for s in SMELL_CATALOG} == expected


class TestBlocksPlanCreate:
    def test_empty_findings_does_not_block(self):
        assert blocks_plan_create([]) is False

    def test_e_severity_finding_blocks(self):
        findings = detect_smells("The system shall be fast and simple.")
        assert blocks_plan_create(findings) is True

    def test_clean_spec_does_not_block(self):
        findings = detect_smells("pytest: tests/test_service.py")
        assert blocks_plan_create(findings) is False
