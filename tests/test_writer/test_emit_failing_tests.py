"""Tests for bob3.orchestrator.test_writer_agent.emit_failing_tests (plural).

Validates the bulk emission path: emit_failing_tests accepts a feature_id and
a list of acceptance criteria, emitting one failing pytest file per AC.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.orchestrator.test_writer_agent import EmittedTest, emit_failing_tests


class TestEmitFailingTests:
    def test_returns_list_of_emitted_tests(self, tmp_path):
        """emit_failing_tests must return a list of EmittedTest objects."""
        results = emit_failing_tests(
            "feat-bulk-return",
            ["File exists: src/a.py", "Function defined: bob3.mod.fn"],
            workspace=tmp_path,
        )
        assert isinstance(results, list)
        assert all(isinstance(r, EmittedTest) for r in results)

    def test_one_test_per_ac(self, tmp_path):
        """Number of emitted tests must equal number of ACs."""
        acs = ["File exists: src/a.py", "File exists: src/b.py", "File exists: src/c.py"]
        results = emit_failing_tests("feat-count", acs, workspace=tmp_path)
        assert len(results) == len(acs)

    def test_empty_ac_list_returns_empty_list(self, tmp_path):
        """An empty AC list must return an empty list without raising."""
        results = emit_failing_tests("feat-empty-acs", [], workspace=tmp_path)
        assert results == []

    def test_all_test_files_exist_on_disk(self, tmp_path):
        """Every emitted test file must be written to disk."""
        acs = ["File exists: src/x.py", "pytest: tests/test_x.py"]
        results = emit_failing_tests("feat-bulk-exists", acs, workspace=tmp_path)
        for et in results:
            assert et.test_path.exists(), f"Missing: {et.test_path}"

    def test_test_files_placed_under_feature_dir(self, tmp_path):
        """All test files must be under tests/<feature_id>/."""
        feature_id = "feat-placement-bulk"
        acs = ["File exists: src/a.py", "File exists: src/b.py"]
        results = emit_failing_tests(feature_id, acs, workspace=tmp_path)
        expected_dir = tmp_path / "tests" / feature_id
        for et in results:
            assert et.test_path.parent == expected_dir

    def test_init_py_created_once(self, tmp_path):
        """An __init__.py must exist in the feature dir after emission."""
        feature_id = "feat-bulk-init"
        emit_failing_tests(feature_id, ["File exists: src/x.py"], workspace=tmp_path)
        init_path = tmp_path / "tests" / feature_id / "__init__.py"
        assert init_path.exists()

    def test_each_test_file_contains_pytest_fail(self, tmp_path):
        """Every emitted test must contain a pytest.fail() call (red test)."""
        acs = ["File exists: src/a.py", "Function defined: bob3.x.y"]
        results = emit_failing_tests("feat-red-all", acs, workspace=tmp_path)
        for et in results:
            content = et.test_path.read_text()
            assert "pytest.fail" in content, f"No pytest.fail in {et.test_path}"

    def test_each_test_file_is_valid_python(self, tmp_path):
        """Every emitted test must parse without SyntaxError."""
        import ast
        acs = ["File exists: src/a.py", "pytest: tests/test_b.py"]
        results = emit_failing_tests("feat-syntax-all", acs, workspace=tmp_path)
        for et in results:
            source = et.test_path.read_text()
            ast.parse(source)  # raises SyntaxError on failure

    def test_ac_indices_are_sequential(self, tmp_path):
        """EmittedTest.ac_index must match the position in the input list."""
        acs = ["AC zero", "AC one", "AC two"]
        results = emit_failing_tests("feat-index", acs, workspace=tmp_path)
        for expected_idx, et in enumerate(results):
            assert et.ac_index == expected_idx

    def test_ac_text_preserved_in_emitted_test(self, tmp_path):
        """Each EmittedTest must store the original AC text."""
        acs = ["File exists: src/alpha.py", "Function defined: bob3.beta.gamma"]
        results = emit_failing_tests("feat-ac-text", acs, workspace=tmp_path)
        for ac, et in zip(acs, results):
            assert et.ac_text == ac

    def test_feature_id_stored_in_each_emitted_test(self, tmp_path):
        """EmittedTest.feature_id must match the input feature_id."""
        feature_id = "feat-id-stored"
        results = emit_failing_tests(feature_id, ["File exists: src/x.py"], workspace=tmp_path)
        for et in results:
            assert et.feature_id == feature_id

    def test_default_workspace_uses_cwd(self, tmp_path, monkeypatch):
        """When workspace is None, files are written relative to cwd."""
        monkeypatch.chdir(tmp_path)
        results = emit_failing_tests("feat-cwd-bulk", ["File exists: src/x.py"])
        assert len(results) == 1
        assert results[0].test_path.exists()
