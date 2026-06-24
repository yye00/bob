"""Tests for bob76.artifact_verifier.verify_ac_artifacts.

Verifies that the bob76 package exposes verify_ac_artifacts which delegates
to the underlying AC artifact-existence checking logic.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from bob76.artifact_verifier import verify_ac_artifacts


class TestVerifyAcArtifactsEmptyAndMinimal:
    def test_empty_list_returns_empty(self):
        result = verify_ac_artifacts([], workspace="/tmp")
        assert result == []

    def test_single_empty_string_returns_list(self):
        result = verify_ac_artifacts([""], workspace="/tmp")
        assert isinstance(result, list)

    def test_whitespace_only_ac_returns_list(self):
        result = verify_ac_artifacts(["   "], workspace="/tmp")
        assert isinstance(result, list)


class TestVerifyAcArtifactsFileExists:
    def test_file_exists_ac_passes_when_file_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            (ws / "myfile.py").write_text("# exists")
            result = verify_ac_artifacts(["File exists: myfile.py"], workspace=ws)
            assert result == []

    def test_file_exists_ac_fails_when_file_missing(self):
        result = verify_ac_artifacts(
            ["File exists: totally_nonexistent_file_abc123.py"],
            workspace="/tmp",
        )
        assert len(result) == 1
        assert result[0].kind == "file_exists"
        assert "ARTIFACT_MISSING" in result[0].reason

    def test_file_exists_absolute_path_rejected(self):
        result = verify_ac_artifacts(["File exists: /etc/passwd"], workspace="/tmp")
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_file_exists_path_traversal_rejected(self):
        result = verify_ac_artifacts(
            ["File exists: ../../etc/passwd"], workspace="/tmp"
        )
        assert isinstance(result, list)
        assert len(result) >= 1


class TestVerifyAcArtifactsPytest:
    def test_pytest_ac_fails_when_file_missing(self):
        result = verify_ac_artifacts(
            ["pytest: tests/nonexistent_test_file_xyz.py"], workspace="/tmp"
        )
        assert len(result) == 1
        assert result[0].kind == "pytest"
        assert "ARTIFACT_MISSING" in result[0].reason

    def test_pytest_ac_passes_when_test_file_present_with_tests(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            test_dir = ws / "tests"
            test_dir.mkdir()
            (test_dir / "test_sample.py").write_text(
                "def test_something():\n    assert True\n"
            )
            result = verify_ac_artifacts(
                ["pytest: tests/test_sample.py"], workspace=ws
            )
            assert result == []

    def test_pytest_ac_empty_path_is_miss(self):
        result = verify_ac_artifacts(["pytest:"], workspace="/tmp")
        assert isinstance(result, list)


class TestVerifyAcArtifactsFunctionDefined:
    def test_function_defined_ac_passes_for_real_symbol(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            src = ws / "src"
            src.mkdir()
            pkg = src / "mypkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("")
            (pkg / "mymod.py").write_text("def my_func(): pass\n")
            result = verify_ac_artifacts(
                ["Function defined: mypkg.mymod.my_func"], workspace=ws
            )
            assert result == []

    def test_function_defined_ac_fails_for_missing_symbol(self):
        result = verify_ac_artifacts(
            ["Function defined: nonexistent_pkg_xyz.module.func"],
            workspace="/tmp",
        )
        assert len(result) == 1
        assert result[0].kind == "function_defined"


class TestVerifyAcArtifactsUnknownPrefix:
    def test_unknown_prefix_returns_miss(self):
        result = verify_ac_artifacts(
            ["some_unknown_prefix: value"], workspace="/tmp"
        )
        assert len(result) >= 1
        assert result[0].kind == "unknown_prefix"

    def test_integration_prefix_flagged_as_unknown(self):
        result = verify_ac_artifacts(
            ["integration: bob3.acceptance.characterization"], workspace="/tmp"
        )
        assert len(result) >= 1
        assert result[0].kind == "unknown_prefix"


class TestVerifyAcArtifactsMultiple:
    def test_multiple_acs_all_missing_returns_all_misses(self):
        result = verify_ac_artifacts(
            [
                "File exists: missing_a.py",
                "File exists: missing_b.py",
            ],
            workspace="/tmp",
        )
        assert len(result) == 2

    def test_mixed_passing_and_failing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            (ws / "present.py").write_text("# here")
            result = verify_ac_artifacts(
                [
                    "File exists: present.py",
                    "File exists: absent.py",
                ],
                workspace=ws,
            )
            assert len(result) == 1
            assert result[0].expected_path == "absent.py"


class TestVerifyAcArtifactsInvalidInput:
    def test_non_list_raises(self):
        with pytest.raises((ValueError, TypeError)):
            verify_ac_artifacts("File exists: foo.py", workspace="/tmp")  # type: ignore

    def test_none_acs_raises(self):
        with pytest.raises((ValueError, TypeError)):
            verify_ac_artifacts(None, workspace="/tmp")  # type: ignore

    def test_none_workspace_raises(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            verify_ac_artifacts([], workspace=None)  # type: ignore

    def test_non_string_item_raises(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            verify_ac_artifacts([42], workspace="/tmp")  # type: ignore


class TestArtifactMissFields:
    def test_miss_has_required_fields(self):
        result = verify_ac_artifacts(["File exists: no_such_file.py"], workspace="/tmp")
        assert len(result) == 1
        miss = result[0]
        assert hasattr(miss, "ac_text")
        assert hasattr(miss, "expected_path")
        assert hasattr(miss, "kind")
        assert hasattr(miss, "reason")

    def test_miss_reason_contains_artifact_missing(self):
        result = verify_ac_artifacts(["File exists: no_such_file.py"], workspace="/tmp")
        assert len(result) == 1
        assert "ARTIFACT_MISSING" in result[0].reason
