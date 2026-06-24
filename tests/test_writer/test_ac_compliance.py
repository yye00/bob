"""AC compliance tests for the test-writer sub-agent feature.

Verifies that the feature 22f9a7a5-96c3-4dd6-a228-168e1923ec92 acceptance
criteria are satisfied:
  - src/bob3/test_writer.py exists
  - bob3.test_writer.TestWriter is importable and callable
  - integration with bob3.orchestrator (run_loop imports emit_failing_tests)
"""

from __future__ import annotations

import importlib
from pathlib import Path


class TestFileExists:
    def test_test_writer_module_file_exists(self):
        """AC: File exists: src/bob3/test_writer.py"""
        module_file = Path(__file__).parent.parent.parent / "src" / "bob3" / "test_writer.py"
        assert module_file.exists(), f"Expected {module_file} to exist"


class TestWriterClass:
    def test_testwriter_class_importable(self):
        """AC: Function defined: bob3.test_writer.TestWriter"""
        from bob3.test_writer import TestWriter  # noqa: F401 — import is the assertion

    def test_testwriter_class_has_run_method(self):
        """TestWriter.run is the main entry point."""
        from bob3.test_writer import TestWriter
        tw = TestWriter()
        assert callable(tw.run), "TestWriter.run must be callable"

    def test_testwriter_run_emits_tests(self, tmp_path):
        """TestWriter.run returns a dict with emitted, filter_results, bijection, gate_passed."""
        from bob3.test_writer import TestWriter
        tw = TestWriter()
        result = tw.run(
            "ac-compliance-feature",
            ["File exists: src/bob3/test_writer.py"],
            workspace=tmp_path,
        )
        assert isinstance(result, dict)
        assert "emitted" in result
        assert "filter_results" in result
        assert "bijection" in result
        assert "gate_passed" in result
        assert len(result["emitted"]) == 1

    def test_testwriter_run_empty_acs_is_valid(self, tmp_path):
        """TestWriter.run with empty AC list returns gate_passed=True."""
        from bob3.test_writer import TestWriter
        tw = TestWriter()
        result = tw.run("ac-compliance-empty", [], workspace=tmp_path)
        assert result["gate_passed"] is True
        assert result["emitted"] == []

    def test_testwriter_run_invalid_feature_id_raises(self, tmp_path):
        """TestWriter.run with empty feature_id raises ValueError."""
        import pytest
        from bob3.test_writer import TestWriter
        tw = TestWriter()
        with pytest.raises(ValueError, match="feature_id"):
            tw.run("", ["File exists: src/x.py"], workspace=tmp_path)


class TestOrchestratorIntegration:
    def test_run_loop_imports_emit_failing_tests(self):
        """AC: integration: bob3.orchestrator — run_loop imports emit_failing_tests."""
        import bob3.orchestrator.run_loop as run_loop_module
        assert hasattr(run_loop_module, "_emit_failing_tests") or \
               "emit_failing_tests" in dir(run_loop_module) or \
               "_emit_failing_tests" in vars(run_loop_module), \
               "run_loop must import emit_failing_tests from test_writer_agent"

    def test_test_writer_agent_module_importable(self):
        """bob3.orchestrator.test_writer_agent must be importable."""
        mod = importlib.import_module("bob3.orchestrator.test_writer_agent")
        assert hasattr(mod, "emit_failing_tests")
        assert hasattr(mod, "triple_filter")
        assert hasattr(mod, "verify_bijection")
        assert hasattr(mod, "generate_failing_tests")

    def test_test_writer_module_exports_all_public_api(self):
        """bob3.test_writer must re-export the full public API."""
        import bob3.test_writer as tw_mod
        required = [
            "TestWriter",
            "emit_failing_test",
            "triple_filter_one",
            "spawn_test_writer_subagent",
            "emit_failing_tests",
            "triple_filter",
            "verify_bijection",
            "generate_failing_tests",
        ]
        for name in required:
            assert hasattr(tw_mod, name), f"bob3.test_writer missing: {name}"
