"""Tests that emit_failing_tests writes exactly one test file per AC."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from bob3.orchestrator.test_writer_agent import EmittedTest, emit_failing_tests


class TestEmitFailingTestsOnePerAC:
    def test_emits_one_file_per_ac(self, tmp_path):
        acs = [
            "File exists: src/bob3/foo.py",
            "Function defined: bob3.foo.bar",
            "pytest: tests/test_foo.py",
        ]
        results = emit_failing_tests("feat-abc123", acs, workspace=tmp_path)
        assert len(results) == 3

    def test_files_actually_exist_on_disk(self, tmp_path):
        acs = ["File exists: src/mymod.py", "pytest: tests/test_mymod.py"]
        results = emit_failing_tests("feat-xyz", acs, workspace=tmp_path)
        for r in results:
            assert r.test_path.exists(), f"Expected {r.test_path} to exist"

    def test_output_dir_contains_init(self, tmp_path):
        acs = ["File exists: src/x.py"]
        emit_failing_tests("feat-001", acs, workspace=tmp_path)
        init = tmp_path / "tests" / "feat-001" / "__init__.py"
        assert init.exists()

    def test_empty_ac_list_returns_empty(self, tmp_path):
        results = emit_failing_tests("feat-empty", [], workspace=tmp_path)
        assert results == []

    def test_returns_emitted_test_dataclass(self, tmp_path):
        acs = ["Function defined: bob3.core.run"]
        results = emit_failing_tests("feat-type-check", acs, workspace=tmp_path)
        assert len(results) == 1
        r = results[0]
        assert isinstance(r, EmittedTest)
        assert r.feature_id == "feat-type-check"
        assert r.ac_index == 0
        assert r.ac_text == "Function defined: bob3.core.run"

    def test_test_file_contains_pytest_fail(self, tmp_path):
        acs = ["File exists: src/example.py"]
        results = emit_failing_tests("feat-content", acs, workspace=tmp_path)
        content = results[0].test_path.read_text()
        assert "pytest.fail" in content

    def test_test_path_follows_naming_convention(self, tmp_path):
        acs = ["pytest: tests/test_foo.py"]
        results = emit_failing_tests("feat-naming", acs, workspace=tmp_path)
        name = results[0].test_path.name
        assert name.startswith("test_ac_0_")
        assert name.endswith(".py")

    def test_multiple_acs_have_distinct_file_names(self, tmp_path):
        acs = ["File exists: src/a.py", "File exists: src/b.py", "pytest: tests/test_c.py"]
        results = emit_failing_tests("feat-distinct", acs, workspace=tmp_path)
        names = [r.test_path.name for r in results]
        assert len(set(names)) == len(names), "Duplicate test file names detected"

    def test_idempotent_rerun_does_not_fail(self, tmp_path):
        acs = ["Function defined: bob3.mod.fn"]
        emit_failing_tests("feat-idem", acs, workspace=tmp_path)
        results = emit_failing_tests("feat-idem", acs, workspace=tmp_path)
        assert len(results) == 1
        assert results[0].test_path.exists()
