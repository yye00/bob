"""Tests for TestWriterAgent — full pipeline (AC: test_writer_agent).

Validates the end-to-end test-writer sub-agent pipeline: emit, filter, and
bijection checks via the TestWriterAgent facade.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from test_writer import TestWriterAgent
from bob3.orchestrator.test_writer_agent import (
    EmittedTest,
    FilterResult,
    BijectionReport,
    emit_failing_tests,
    generate_failing_tests,
    verify_bijection,
    triple_filter,
)


class TestTestWriterAgent:
    def test_generate_returns_expected_keys(self, tmp_path):
        """generate() must return a dict with emitted, filter_results, bijection, gate_passed."""
        agent = TestWriterAgent(workspace=tmp_path)
        result = agent.generate("feat-keys-check", ["File exists: src/bob3/x.py"])
        assert set(result.keys()) == {"emitted", "filter_results", "bijection", "gate_passed"}

    def test_generate_emits_one_test_per_ac(self, tmp_path):
        """generate() must emit exactly one test file per acceptance criterion."""
        agent = TestWriterAgent(workspace=tmp_path)
        acs = ["File exists: src/a.py", "Function defined: mod.fn", "pytest: tests/test_b.py"]
        result = agent.generate("feat-one-per-ac", acs)
        assert len(result["emitted"]) == 3
        assert len(result["filter_results"]) == 3

    def test_emitted_test_files_exist_on_disk(self, tmp_path):
        """Every EmittedTest.test_path must point to a real file."""
        agent = TestWriterAgent(workspace=tmp_path)
        emitted = agent.emit("feat-disk-check", ["File exists: src/foo.py"])
        for et in emitted:
            assert et.test_path.exists(), f"Expected {et.test_path} to exist"

    def test_emitted_tests_placed_under_feature_dir(self, tmp_path):
        """Test files must be under tests/<feature_id>/."""
        feature_id = "feat-dir-check"
        agent = TestWriterAgent(workspace=tmp_path)
        emitted = agent.emit(feature_id, ["File exists: src/foo.py"])
        expected_parent = tmp_path / "tests" / feature_id
        for et in emitted:
            assert et.test_path.parent == expected_parent

    def test_gate_passed_true_for_well_formed_acs(self, tmp_path):
        """gate_passed must be True for well-formed ACs that produce valid failing tests."""
        agent = TestWriterAgent(workspace=tmp_path)
        result = agent.generate("feat-gate-ok", ["Function defined: bob3.module.fn"])
        assert result["gate_passed"] is True

    def test_bijection_is_bijective_after_emit(self, tmp_path):
        """verify_bijection must confirm bijection after emit_failing_tests."""
        acs = ["File exists: src/a.py", "pytest: tests/test_b.py"]
        emit_failing_tests("feat-bij", acs, workspace=tmp_path)
        report = verify_bijection("feat-bij", acs, workspace=tmp_path)
        assert report.is_bijective is True
        assert report.missing_tests == []
        assert report.orphan_tests == []

    def test_filter_accepts_all_emitted_tests(self, tmp_path):
        """triple_filter must accept all tests emitted by emit_failing_tests."""
        acs = ["File exists: src/x.py"]
        emitted = emit_failing_tests("feat-filter-accept", acs, workspace=tmp_path)
        results = triple_filter(emitted, workspace=tmp_path)
        for r in results:
            assert r.accepted, f"Expected {r.test_path} to be accepted, reason: {r.reason}"

    def test_generate_failing_tests_module_level_import(self, tmp_path):
        """generate_failing_tests must be importable from test_writer at module level."""
        from test_writer import generate_failing_tests as gft
        result = gft("feat-module-import", ["File exists: src/z.py"], workspace=tmp_path)
        assert isinstance(result, dict)
        assert "gate_passed" in result

    def test_empty_acs_returns_gate_passed_true(self, tmp_path):
        """generate() with empty AC list must return gate_passed=True."""
        agent = TestWriterAgent(workspace=tmp_path)
        result = agent.generate("feat-empty-acs", [])
        assert result["gate_passed"] is True
        assert result["emitted"] == []

    def test_agent_uses_workspace_for_test_paths(self, tmp_path):
        """TestWriterAgent must write tests inside the provided workspace."""
        agent = TestWriterAgent(workspace=tmp_path)
        emitted = agent.emit("feat-workspace", ["File exists: src/w.py"])
        for et in emitted:
            assert str(et.test_path).startswith(str(tmp_path))
