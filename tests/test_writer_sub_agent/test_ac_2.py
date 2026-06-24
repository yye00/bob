"""Tests for AC-2: TestWriterAgent integration with spec_critic pipeline.

Verifies that the TestWriterAgent inserts correctly between spec_critic and
the implementer — receiving spec-critic output (acceptance criteria list) and
emitting one failing test per AC, which can then be handed to the implementer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from test_writer import TestWriterAgent
from bob.orchestrator.test_writer_agent import (
    FilterResult,
    emit_failing_tests,
    triple_filter,
    verify_bijection,
)


class TestTestWriterAgentSpecCriticIntegration:
    def test_agent_emit_returns_emitted_tests(self, tmp_path):
        """emit() must return a list of EmittedTest objects, one per AC."""
        acs = ["File exists: src/spec_critic/output.py", "Function defined: bob.spec_critic.run"]
        agent = TestWriterAgent(workspace=tmp_path)
        emitted = agent.emit("feat-ac2-emit", acs)
        assert len(emitted) == 2
        for et in emitted:
            assert et.test_path.exists()
            assert et.feature_id == "feat-ac2-emit"

    def test_agent_filter_returns_filter_results(self, tmp_path):
        """filter() must return a FilterResult per emitted test."""
        acs = ["File exists: src/spec_critic/output.py"]
        agent = TestWriterAgent(workspace=tmp_path)
        emitted = agent.emit("feat-ac2-filter", acs)
        results = agent.filter(emitted)
        assert len(results) == len(emitted)
        for r in results:
            assert isinstance(r, FilterResult)

    def test_agent_validate_returns_bijection_report(self, tmp_path):
        """validate() must return a BijectionReport after emit()."""
        acs = ["File exists: src/spec_critic/run.py"]
        agent = TestWriterAgent(workspace=tmp_path)
        agent.emit("feat-ac2-validate", acs)
        report = agent.validate("feat-ac2-validate", acs)
        assert report.is_bijective is True
        assert report.missing_tests == []
        assert report.orphan_tests == []

    def test_pipeline_emit_filter_validate_consistent(self, tmp_path):
        """Running emit → filter → validate manually produces the same result as generate()."""
        acs = ["File exists: src/spec_critic/spec.py", "pytest: tests/test_spec_critic.py"]
        fid = "feat-ac2-pipeline"
        agent = TestWriterAgent(workspace=tmp_path)

        # Manual pipeline
        emitted = emit_failing_tests(fid, acs, workspace=tmp_path)
        filter_results = triple_filter(emitted, workspace=tmp_path)
        bijection = verify_bijection(fid, acs, workspace=tmp_path)

        # generate() must produce the same structural outcome
        agent2 = TestWriterAgent(workspace=tmp_path / "gen")
        result = agent2.generate(fid, acs)

        assert len(result["emitted"]) == len(emitted)
        assert len(result["filter_results"]) == len(filter_results)
        assert result["bijection"].is_bijective == bijection.is_bijective

    def test_accepted_tests_are_all_green_in_filter_results(self, tmp_path):
        """All filter results must have accepted=True for standard AC strings."""
        acs = [
            "File exists: src/spec_critic/__init__.py",
            "Function defined: spec_critic.run_critic",
        ]
        agent = TestWriterAgent(workspace=tmp_path)
        result = agent.generate("feat-ac2-accept", acs)
        for r in result["filter_results"]:
            assert r.accepted, (
                f"filter rejected {r.test_path}: {r.reason}"
            )

    def test_workspace_is_used_for_test_output(self, tmp_path):
        """Tests must be written into the agent's workspace, not cwd."""
        workspace = tmp_path / "my_project"
        workspace.mkdir()
        agent = TestWriterAgent(workspace=workspace)
        result = agent.generate("feat-ac2-workspace", ["File exists: src/foo.py"])
        for et in result["emitted"]:
            assert str(workspace) in str(et.test_path), (
                f"Test path {et.test_path} is not under workspace {workspace}"
            )
