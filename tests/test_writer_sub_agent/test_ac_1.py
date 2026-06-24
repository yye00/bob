"""Tests for AC-1: TestWriterAgent.generate — emits one failing pytest per AC.

Verifies that TestWriterAgent.generate writes one failing test file per
acceptance criterion under tests/<feature_id>/test_<ac_id>.py, and that
the AC-to-test mapping is bijective.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from test_writer import TestWriterAgent
from bob.orchestrator.test_writer_agent import EmittedTest, BijectionReport


class TestTestWriterAgentGenerate:
    def test_generate_returns_expected_keys(self, tmp_path):
        """generate() must return a dict with emitted, filter_results, bijection, gate_passed."""
        agent = TestWriterAgent(workspace=tmp_path)
        result = agent.generate("feat-ac1-keys", ["File exists: src/x.py"])
        assert set(result.keys()) >= {"emitted", "filter_results", "bijection", "gate_passed"}

    def test_generate_emits_one_file_per_ac(self, tmp_path):
        """generate() must emit exactly one test file per AC."""
        acs = ["File exists: src/a.py", "Function defined: bob.a.fn"]
        agent = TestWriterAgent(workspace=tmp_path)
        result = agent.generate("feat-ac1-count", acs)
        assert len(result["emitted"]) == 2
        for et in result["emitted"]:
            assert isinstance(et, EmittedTest)
            assert et.test_path.exists()

    def test_generated_test_files_under_feature_dir(self, tmp_path):
        """test files must reside under tests/<feature_id>/."""
        agent = TestWriterAgent(workspace=tmp_path)
        result = agent.generate("feat-ac1-dir", ["File exists: src/mod.py"])
        for et in result["emitted"]:
            assert et.test_path.parent == tmp_path / "tests" / "feat-ac1-dir"

    def test_generate_bijection_is_satisfied(self, tmp_path):
        """Every AC must have exactly one test file — bijection must be satisfied."""
        acs = ["File exists: src/x.py", "pytest: tests/test_x.py"]
        agent = TestWriterAgent(workspace=tmp_path)
        result = agent.generate("feat-ac1-bijection", acs)
        assert isinstance(result["bijection"], BijectionReport)
        assert result["bijection"].is_bijective is True

    def test_generate_gate_passed_for_valid_acs(self, tmp_path):
        """gate_passed must be True when all triple-filter checks pass."""
        agent = TestWriterAgent(workspace=tmp_path)
        result = agent.generate("feat-ac1-gate", ["File exists: src/mymod.py"])
        assert result["gate_passed"] is True

    def test_generate_emitted_tests_fail_on_stub(self, tmp_path):
        """Emitted tests must fail on stub code (genuinely red before implementation)."""
        from bob.orchestrator.test_writer_agent import _check_fails_on_stub
        agent = TestWriterAgent(workspace=tmp_path)
        result = agent.generate("feat-ac1-stub", ["Function defined: bob.x.fn"])
        for et in result["emitted"]:
            assert _check_fails_on_stub(et.test_path), (
                f"{et.test_path} must fail on stub — it must be genuinely red"
            )

    def test_generate_with_empty_acs_returns_bijective_empty(self, tmp_path):
        """Zero ACs must return gate_passed=True with an empty bijective report."""
        agent = TestWriterAgent(workspace=tmp_path)
        result = agent.generate("feat-ac1-empty", [])
        assert result["emitted"] == []
        assert result["gate_passed"] is True
        assert result["bijection"].is_bijective is True
