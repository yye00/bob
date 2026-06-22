"""Tests for bob3.ac_artifact_verifier.verify_ac_artifacts.

Feature: AC artifact-existence verifier — refuse to pass AC when referenced files are missing.
Pre-pytest pass MUST verify that every AC of the form
`pytest: <path>`, `File exists: <path>`, `File modified: <path>`,
or `Function defined: <module>.<symbol>` resolves to an actual artifact.
Missing artifact -> AC fails with reason ARTIFACT_MISSING:<path>.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from bob3.ac_artifact_verifier import ArtifactMiss, verify_ac_artifacts


class TestVerifyAcArtifactsBasic:
    def test_empty_list_returns_empty(self):
        result = verify_ac_artifacts([], workspace="/tmp")
        assert result == []

    def test_returns_list(self):
        result = verify_ac_artifacts([], workspace="/tmp")
        assert isinstance(result, list)

    def test_missing_file_returns_miss(self):
        result = verify_ac_artifacts(
            ["File exists: definitely_not_there_abc123.py"],
            workspace="/tmp",
        )
        assert len(result) == 1
        assert isinstance(result[0], ArtifactMiss)

    def test_missing_file_reason_contains_artifact_missing(self):
        result = verify_ac_artifacts(
            ["File exists: missing_file.py"],
            workspace="/tmp",
        )
        assert len(result) == 1
        assert "ARTIFACT_MISSING" in result[0].reason

    def test_present_file_returns_no_miss(self):
        ws = Path(tempfile.mkdtemp())
        (ws / "present.py").write_text("# exists")
        result = verify_ac_artifacts(["File exists: present.py"], workspace=ws)
        assert result == []

    def test_multiple_acs_all_missing(self):
        result = verify_ac_artifacts(
            ["File exists: gone_a.py", "File exists: gone_b.py"],
            workspace="/tmp",
        )
        assert len(result) == 2

    def test_multiple_acs_mixed(self):
        ws = Path(tempfile.mkdtemp())
        (ws / "here.py").write_text("# exists")
        result = verify_ac_artifacts(
            ["File exists: here.py", "File exists: not_here.py"],
            workspace=ws,
        )
        assert len(result) == 1
        assert "not_here.py" in result[0].expected_path


class TestPytestAc:
    def test_missing_pytest_file_returns_miss(self):
        result = verify_ac_artifacts(
            ["pytest: tests/no_such_test_file.py"],
            workspace="/tmp",
        )
        assert len(result) == 1
        assert result[0].kind == "pytest"

    def test_pytest_ac_with_no_tests_returns_miss(self, tmp_path):
        (tmp_path / "empty_test.py").write_text("# no test functions here")
        result = verify_ac_artifacts(
            ["pytest: empty_test.py"],
            workspace=tmp_path,
        )
        assert len(result) == 1

    def test_pytest_ac_with_real_tests_returns_no_miss(self, tmp_path):
        (tmp_path / "real_test.py").write_text(
            "def test_something():\n    assert True\n"
        )
        result = verify_ac_artifacts(
            ["pytest: real_test.py"],
            workspace=tmp_path,
        )
        assert result == []

    def test_pytest_ac_missing_reason_artifact_missing(self):
        result = verify_ac_artifacts(
            ["pytest: no_such_file.py"],
            workspace="/tmp",
        )
        assert len(result) == 1
        assert "ARTIFACT_MISSING" in result[0].reason


class TestFunctionDefinedAc:
    def test_missing_function_returns_miss(self):
        result = verify_ac_artifacts(
            ["Function defined: bob3.ac_artifact_verifier.nonexistent_function_xyz"],
            workspace="/home/yelkhamr/dark-factory/bob85",
        )
        assert len(result) == 1
        assert result[0].kind == "function_defined"

    def test_present_function_returns_no_miss(self):
        result = verify_ac_artifacts(
            ["Function defined: bob3.ac_artifact_verifier.verify_ac_artifacts"],
            workspace="/home/yelkhamr/dark-factory/bob85",
        )
        assert result == []

    def test_missing_module_returns_miss(self):
        result = verify_ac_artifacts(
            ["Function defined: bob3.nonexistent_module_xyz.some_func"],
            workspace="/home/yelkhamr/dark-factory/bob85",
        )
        assert len(result) == 1


class TestUnknownPrefix:
    def test_unknown_prefix_produces_miss(self):
        result = verify_ac_artifacts(
            ["unknown_prefix: some_value"],
            workspace="/tmp",
        )
        assert len(result) == 1
        assert result[0].kind == "unknown_prefix"

    def test_integration_prefix_produces_miss(self):
        result = verify_ac_artifacts(
            ["integration: bob3.orchestrator"],
            workspace="/tmp",
        )
        assert len(result) == 1
        assert result[0].kind == "unknown_prefix"


class TestArtifactMissFields:
    def test_miss_has_ac_text(self):
        ac = "File exists: absent_file.py"
        result = verify_ac_artifacts([ac], workspace="/tmp")
        assert len(result) == 1
        assert result[0].ac_text == ac

    def test_miss_has_expected_path(self):
        result = verify_ac_artifacts(
            ["File exists: absent_file.py"],
            workspace="/tmp",
        )
        assert len(result) == 1
        assert "absent_file.py" in result[0].expected_path

    def test_miss_has_kind(self):
        result = verify_ac_artifacts(
            ["File exists: absent_file.py"],
            workspace="/tmp",
        )
        assert len(result) == 1
        assert result[0].kind == "file_exists"

    def test_miss_has_reason(self):
        result = verify_ac_artifacts(
            ["File exists: absent_file.py"],
            workspace="/tmp",
        )
        assert len(result) == 1
        assert result[0].reason


class TestInputValidation:
    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError):
            verify_ac_artifacts("File exists: foo.py", workspace="/tmp")  # type: ignore[arg-type]

    def test_none_acs_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            verify_ac_artifacts(None, workspace="/tmp")  # type: ignore[arg-type]

    def test_none_workspace_raises_value_error(self):
        with pytest.raises(ValueError):
            verify_ac_artifacts([], workspace=None)  # type: ignore[arg-type]

    def test_non_string_in_list_raises_type_error(self):
        with pytest.raises(TypeError):
            verify_ac_artifacts([42], workspace="/tmp")  # type: ignore[list-item]

    def test_workspace_as_string_accepted(self):
        result = verify_ac_artifacts([], workspace="/tmp")
        assert result == []

    def test_workspace_as_path_accepted(self, tmp_path):
        result = verify_ac_artifacts([], workspace=tmp_path)
        assert result == []
