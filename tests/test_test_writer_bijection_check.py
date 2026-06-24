"""Tests for verify_bijection — every AC maps to exactly one test, vice versa."""

from __future__ import annotations

from pathlib import Path

import pytest

from bob.orchestrator.test_writer_agent import (
    BijectionReport,
    emit_failing_tests,
    verify_bijection,
)


class TestVerifyBijectionAfterEmit:
    def test_bijection_holds_after_emit(self, tmp_path):
        acs = ["File exists: src/mod.py", "pytest: tests/test_mod.py"]
        emit_failing_tests("feat-bij-ok", acs, workspace=tmp_path)
        report = verify_bijection("feat-bij-ok", acs, workspace=tmp_path)
        assert report.is_bijective is True
        assert report.missing_tests == []
        assert report.orphan_tests == []

    def test_missing_test_detected(self, tmp_path):
        acs = ["File exists: src/a.py", "Function defined: bob.a.fn"]
        emit_failing_tests("feat-missing", acs, workspace=tmp_path)
        # Remove one test file
        out_dir = tmp_path / "tests" / "feat-missing"
        removed = sorted(out_dir.glob("test_ac_1_*.py"))
        assert removed, "Expected at least one test_ac_1 file"
        removed[0].unlink()
        report = verify_bijection("feat-missing", acs, workspace=tmp_path)
        assert report.is_bijective is False
        assert len(report.missing_tests) == 1

    def test_orphan_test_detected(self, tmp_path):
        acs = ["File exists: src/b.py"]
        emit_failing_tests("feat-orphan", acs, workspace=tmp_path)
        # Add an extra file that isn't mapped to any AC
        out_dir = tmp_path / "tests" / "feat-orphan"
        (out_dir / "test_orphan_extra.py").write_text("def test_x(): pass\n")
        report = verify_bijection("feat-orphan", acs, workspace=tmp_path)
        assert report.is_bijective is False
        assert "test_orphan_extra.py" in report.orphan_tests

    def test_returns_bijection_report(self, tmp_path):
        acs = ["pytest: tests/test_q.py"]
        emit_failing_tests("feat-type", acs, workspace=tmp_path)
        report = verify_bijection("feat-type", acs, workspace=tmp_path)
        assert isinstance(report, BijectionReport)

    def test_empty_acs_bijective_with_no_tests(self, tmp_path):
        report = verify_bijection("feat-empty", [], workspace=tmp_path)
        assert report.is_bijective is True
        assert report.missing_tests == []

    def test_ac_ids_populated(self, tmp_path):
        acs = ["File exists: src/x.py", "Function defined: bob.x.go"]
        emit_failing_tests("feat-ids", acs, workspace=tmp_path)
        report = verify_bijection("feat-ids", acs, workspace=tmp_path)
        assert len(report.ac_ids) == 2

    def test_missing_test_dir_reports_all_as_missing(self, tmp_path):
        acs = ["File exists: src/z.py", "pytest: tests/test_z.py"]
        # Do NOT emit — directory does not exist
        report = verify_bijection("feat-nodir", acs, workspace=tmp_path)
        assert report.is_bijective is False
        assert len(report.missing_tests) == 2
