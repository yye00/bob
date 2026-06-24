"""Tests for AC emission: TestWriterAgent.generate emits one failing pytest per AC.

Verifies that generate_failing_tests writes one failing test file per
acceptance criterion under tests/<feature_id>/test_<ac_id>.py, and that
the AC-to-test mapping is bijective.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob.orchestrator.test_writer_agent import (
    BijectionReport,
    EmittedTest,
    emit_failing_tests,
    generate_failing_tests,
    verify_bijection,
)


class TestAcEmission:
    def test_generate_returns_expected_keys(self, tmp_path):
        """generate_failing_tests() must return a dict with emitted, filter_results, bijection, gate_passed."""
        result = generate_failing_tests("feat-emission-keys", ["File exists: src/x.py"], workspace=tmp_path)
        assert set(result.keys()) >= {"emitted", "filter_results", "bijection", "gate_passed"}

    def test_generate_emits_one_file_per_ac(self, tmp_path):
        """generate_failing_tests() must emit exactly one test file per AC."""
        acs = ["File exists: src/a.py", "Function defined: bob.a.fn"]
        result = generate_failing_tests("feat-emission-count", acs, workspace=tmp_path)
        assert len(result["emitted"]) == 2
        for et in result["emitted"]:
            assert isinstance(et, EmittedTest)
            assert et.test_path.exists()

    def test_generated_test_files_under_feature_dir(self, tmp_path):
        """test files must reside under tests/<feature_id>/."""
        result = generate_failing_tests("feat-emission-dir", ["File exists: src/mod.py"], workspace=tmp_path)
        for et in result["emitted"]:
            assert et.test_path.parent == tmp_path / "tests" / "feat-emission-dir"

    def test_generate_bijection_is_satisfied(self, tmp_path):
        """Every AC must have exactly one test file — bijection must be satisfied."""
        acs = ["File exists: src/x.py", "pytest: tests/test_x.py"]
        result = generate_failing_tests("feat-emission-bijection", acs, workspace=tmp_path)
        assert isinstance(result["bijection"], BijectionReport)
        assert result["bijection"].is_bijective is True

    def test_generate_gate_passed_for_valid_acs(self, tmp_path):
        """gate_passed must be True when all triple-filter checks pass."""
        result = generate_failing_tests("feat-emission-gate", ["File exists: src/mymod.py"], workspace=tmp_path)
        assert result["gate_passed"] is True

    def test_generate_with_empty_acs_returns_bijective_empty(self, tmp_path):
        """Zero ACs must return gate_passed=True with an empty bijective report."""
        result = generate_failing_tests("feat-emission-empty", [], workspace=tmp_path)
        assert result["emitted"] == []
        assert result["gate_passed"] is True
        assert result["bijection"].is_bijective is True

    def test_emit_failing_tests_creates_files(self, tmp_path):
        """emit_failing_tests must create test files on disk."""
        acs = ["File exists: src/something.py"]
        emitted = emit_failing_tests("feat-emission-disk", acs, workspace=tmp_path)
        assert len(emitted) == 1
        assert emitted[0].test_path.exists()

    def test_emit_failing_tests_sets_feature_id(self, tmp_path):
        """EmittedTest objects must carry the feature_id."""
        emitted = emit_failing_tests("feat-emission-fid", ["File exists: src/x.py"], workspace=tmp_path)
        assert emitted[0].feature_id == "feat-emission-fid"

    def test_verify_bijection_with_emitted(self, tmp_path):
        """verify_bijection after emit must report is_bijective=True."""
        acs = ["File exists: src/x.py"]
        emit_failing_tests("feat-emission-vbij", acs, workspace=tmp_path)
        report = verify_bijection("feat-emission-vbij", acs, workspace=tmp_path)
        assert report.is_bijective is True
        assert report.missing_tests == []
        assert report.orphan_tests == []
