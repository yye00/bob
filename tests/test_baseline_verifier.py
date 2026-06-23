"""Tests for baseline_verifier.ensure_collection_succeeds.

AC: pytest: tests/test_baseline_verifier.py
AC: Function defined: baseline_verifier.ensure_collection_succeeds
AC: integration: ac_verifier
"""

from __future__ import annotations

import pathlib
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from baseline_verifier import ensure_collection_succeeds


class TestEnsureCollectionSucceedsSignature:
    """Function exists and has the expected callable interface."""

    def test_function_is_callable(self):
        assert callable(ensure_collection_succeeds)

    def test_accepts_workspace_positional(self, tmp_path):
        result = ensure_collection_succeeds(tmp_path)
        assert result is not None

    def test_accepts_none_workspace(self):
        result = ensure_collection_succeeds(None)
        assert result is not None

    def test_accepts_string_workspace(self, tmp_path):
        result = ensure_collection_succeeds(str(tmp_path))
        assert result is not None

    def test_accepts_pathlib_workspace(self, tmp_path):
        result = ensure_collection_succeeds(pathlib.Path(tmp_path))
        assert result is not None


class TestEnsureCollectionSucceedsReturnValue:
    """Return value must have ok, failing_files, and aborted attributes/keys."""

    def test_returns_object_with_ok_attribute(self, tmp_path):
        result = ensure_collection_succeeds(None)
        assert hasattr(result, "ok") or isinstance(result, dict)

    def test_ok_is_true_for_none_workspace(self):
        result = ensure_collection_succeeds(None)
        ok = result.ok if hasattr(result, "ok") else result["ok"]
        assert ok is True

    def test_ok_is_true_for_nonexistent_workspace(self, tmp_path):
        ghost = tmp_path / "nonexistent_dir"
        result = ensure_collection_succeeds(ghost)
        ok = result.ok if hasattr(result, "ok") else result["ok"]
        assert ok is True

    def test_failing_files_is_empty_when_ok(self):
        result = ensure_collection_succeeds(None)
        failing = result.failing_files if hasattr(result, "failing_files") else result.get("failing_files", [])
        assert failing == []


class TestEnsureCollectionSucceedsCleanCollection:
    """When pytest --collect-only exits 0, ok must be True."""

    def _fake_proc(self, returncode: int, stdout: str = "", stderr: str = ""):
        m = MagicMock(spec=subprocess.CompletedProcess)
        m.returncode = returncode
        m.stdout = stdout
        m.stderr = stderr
        return m

    def test_clean_collection_returns_ok_true(self, tmp_path):
        (tmp_path / "tests").mkdir()
        clean_output = "<Module tests/test_ok.py>\n  <Function test_foo>\n"
        with patch("subprocess.run", return_value=self._fake_proc(0, stdout=clean_output)):
            result = ensure_collection_succeeds(tmp_path)
        ok = result.ok if hasattr(result, "ok") else result["ok"]
        assert ok is True

    def test_clean_collection_failing_files_is_empty(self, tmp_path):
        (tmp_path / "tests").mkdir()
        with patch("subprocess.run", return_value=self._fake_proc(0, stdout="")):
            result = ensure_collection_succeeds(tmp_path)
        failing = result.failing_files if hasattr(result, "failing_files") else result.get("failing_files", [])
        assert failing == []


class TestEnsureCollectionSucceedsFailingCollection:
    """When pytest --collect-only exits 2, ok must be False and failing_files populated."""

    def _fake_proc(self, returncode: int, stdout: str = "", stderr: str = ""):
        m = MagicMock(spec=subprocess.CompletedProcess)
        m.returncode = returncode
        m.stdout = stdout
        m.stderr = stderr
        return m

    def test_collection_error_returns_ok_false(self, tmp_path):
        (tmp_path / "tests").mkdir()
        error_output = (
            "ERROR collecting tests/test_broken.py\n"
            "ImportError: No module named 'hypothesis'\n"
        )
        with patch("subprocess.run", return_value=self._fake_proc(2, stdout=error_output)):
            result = ensure_collection_succeeds(tmp_path)
        ok = result.ok if hasattr(result, "ok") else result["ok"]
        assert ok is False

    def test_collection_error_populates_failing_files(self, tmp_path):
        (tmp_path / "tests").mkdir()
        error_output = (
            "ERROR collecting tests/test_broken.py\n"
            "ImportError: No module named 'foo'\n"
        )
        with patch("subprocess.run", return_value=self._fake_proc(2, stdout=error_output)):
            result = ensure_collection_succeeds(tmp_path)
        failing = result.failing_files if hasattr(result, "failing_files") else result.get("failing_files", [])
        assert any("test_broken" in f for f in failing)

    def test_collection_error_raises_on_strict_mode(self, tmp_path):
        (tmp_path / "tests").mkdir()
        error_output = "ERROR collecting tests/test_import_err.py\nImportError: bad\n"
        with patch("subprocess.run", return_value=self._fake_proc(2, stdout=error_output)):
            with pytest.raises(Exception):
                ensure_collection_succeeds(tmp_path, strict=True)


class TestEnsureCollectionSucceedsAcVerifierIntegration:
    """Integration: ac_verifier should use ensure_collection_succeeds."""

    def test_ac_verifier_importable(self):
        from ac_verifier import verify_artifacts  # noqa: F401
        assert callable(verify_artifacts)

    def test_baseline_verifier_re_exported_from_ac_verifier(self):
        import ac_verifier
        assert hasattr(ac_verifier, "ensure_collection_succeeds") or \
               hasattr(ac_verifier, "CollectionResult") or \
               hasattr(ac_verifier, "verify_collection")

    def test_ensure_collection_succeeds_importable_from_baseline_verifier(self):
        from baseline_verifier import ensure_collection_succeeds
        assert callable(ensure_collection_succeeds)


class TestEnsureCollectionSucceedsBoundary:
    """Boundary: missing test_dir returns ok gracefully."""

    def test_missing_tests_dir_returns_ok(self, tmp_path):
        result = ensure_collection_succeeds(tmp_path, test_dir="no_such_dir")
        ok = result.ok if hasattr(result, "ok") else result["ok"]
        assert ok is True

    def test_default_test_dir_used_when_omitted(self, tmp_path):
        result = ensure_collection_succeeds(tmp_path)
        assert result is not None

    def test_custom_test_dir_accepted(self, tmp_path):
        (tmp_path / "mytests").mkdir()
        result = ensure_collection_succeeds(tmp_path, test_dir="mytests")
        assert result is not None


class TestEnsureCollectionSucceedsErrorPath:
    """Error path: invalid inputs raise ValueError."""

    def test_invalid_workspace_type_raises(self):
        with pytest.raises((ValueError, TypeError)):
            ensure_collection_succeeds(42)

    def test_negative_timeout_raises(self, tmp_path):
        with pytest.raises(ValueError):
            ensure_collection_succeeds(tmp_path, timeout=-1)

    def test_zero_timeout_raises(self, tmp_path):
        with pytest.raises(ValueError):
            ensure_collection_succeeds(tmp_path, timeout=0)
