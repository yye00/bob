"""Tests for bob3.artifact_existence_verifier.verify_ac_artifacts.

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

from bob3.artifact_existence_verifier import ArtifactMiss, verify_ac_artifacts


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

    def test_multiple_acs_mixed_present_and_missing(self):
        ws = Path(tempfile.mkdtemp())
        (ws / "here.py").write_text("# exists")
        result = verify_ac_artifacts(
            ["File exists: here.py", "File exists: missing_x.py"],
            workspace=ws,
        )
        assert len(result) == 1
        assert "missing_x.py" in result[0].reason


class TestVerifyAcArtifactsFileTypes:
    def test_file_modified_ac_present(self):
        ws = Path(tempfile.mkdtemp())
        (ws / "mod.py").write_text("# modified")
        result = verify_ac_artifacts(["File modified: mod.py"], workspace=ws)
        assert result == []

    def test_file_modified_ac_missing(self):
        result = verify_ac_artifacts(
            ["File modified: not_here.py"],
            workspace="/tmp",
        )
        assert len(result) == 1
        assert result[0].kind == "file_modified"

    def test_file_modified_or_created_ac_present(self):
        ws = Path(tempfile.mkdtemp())
        (ws / "new.py").write_text("# new")
        result = verify_ac_artifacts(["File modified or created: new.py"], workspace=ws)
        assert result == []

    def test_file_modified_or_created_ac_missing(self):
        result = verify_ac_artifacts(
            ["File modified or created: phantom.py"],
            workspace="/tmp",
        )
        assert len(result) == 1
        assert result[0].kind == "file_modified_or_created"

    def test_pytest_ac_present(self):
        ws = Path(tempfile.mkdtemp())
        test_file = ws / "test_sample.py"
        test_file.write_text("def test_foo():\n    assert True\n")
        result = verify_ac_artifacts([f"pytest: test_sample.py"], workspace=ws)
        assert result == []

    def test_pytest_ac_missing_file(self):
        result = verify_ac_artifacts(
            ["pytest: tests/test_nonexistent.py"],
            workspace="/tmp",
        )
        assert len(result) == 1
        assert result[0].kind == "pytest"
        assert "ARTIFACT_MISSING" in result[0].reason


class TestVerifyAcArtifactsFunctionDefined:
    def test_function_defined_present(self):
        ws = Path("/home/yelkhamr/dark-factory/bob87")
        result = verify_ac_artifacts(
            ["Function defined: bob3.artifact_existence_verifier.verify_ac_artifacts"],
            workspace=ws,
        )
        assert result == []

    def test_function_defined_missing_module(self):
        result = verify_ac_artifacts(
            ["Function defined: bob3.nonexistent_module_xyz.some_func"],
            workspace="/tmp",
        )
        assert len(result) == 1
        assert result[0].kind == "function_defined"

    def test_function_defined_missing_symbol(self):
        ws = Path("/home/yelkhamr/dark-factory/bob87")
        result = verify_ac_artifacts(
            ["Function defined: bob3.artifact_existence_verifier.totally_missing_symbol_xyz"],
            workspace=ws,
        )
        assert len(result) == 1
        assert result[0].kind == "function_defined"


class TestVerifyAcArtifactsUnknownPrefix:
    def test_unknown_prefix_returns_miss(self):
        result = verify_ac_artifacts(
            ["integration: some_module"],
            workspace="/tmp",
        )
        assert len(result) == 1
        assert result[0].kind == "unknown_prefix"

    def test_unknown_prefix_miss_contains_ac_text(self):
        ac = "mystery_prefix: something"
        result = verify_ac_artifacts([ac], workspace="/tmp")
        assert len(result) == 1
        assert ac in result[0].ac_text or ac in result[0].reason


class TestVerifyAcArtifactsInputValidation:
    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError):
            verify_ac_artifacts("File exists: foo.py", workspace="/tmp")  # type: ignore[arg-type]

    def test_none_acs_raises(self):
        with pytest.raises((ValueError, TypeError)):
            verify_ac_artifacts(None, workspace="/tmp")  # type: ignore[arg-type]

    def test_none_workspace_raises(self):
        with pytest.raises((ValueError, TypeError)):
            verify_ac_artifacts([], workspace=None)  # type: ignore[arg-type]

    def test_non_string_item_raises_type_error(self):
        with pytest.raises(TypeError):
            verify_ac_artifacts([42], workspace="/tmp")  # type: ignore[list-item]

    def test_path_traversal_rejected(self):
        result = verify_ac_artifacts(
            ["File exists: ../../etc/passwd"],
            workspace="/tmp",
        )
        assert len(result) >= 1

    def test_absolute_path_rejected(self):
        result = verify_ac_artifacts(
            ["File exists: /etc/passwd"],
            workspace="/tmp",
        )
        assert len(result) >= 1


class TestArtifactMissDataclass:
    def test_artifact_miss_has_required_fields(self):
        miss = ArtifactMiss(
            ac_text="File exists: foo.py",
            expected_path="foo.py",
            kind="file_exists",
            reason="ARTIFACT_MISSING:foo.py",
        )
        assert miss.ac_text == "File exists: foo.py"
        assert miss.expected_path == "foo.py"
        assert miss.kind == "file_exists"
        assert "ARTIFACT_MISSING" in miss.reason
