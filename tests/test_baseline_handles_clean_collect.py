"""Tests for bob.verifier.baseline_capture — clean collection boundary.

Verifies that run_pytest_collect_only returns a CollectResult with ok=True and
empty failing_files when the suite collects without errors (zero/empty boundary).
"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from bob.verifier.baseline_capture import (
    CollectResult,
    handle_clean_collect,
    run_pytest_collect_only,
)


def _fake_proc(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock(spec=subprocess.CompletedProcess)
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


class TestRunPytestCollectOnlyClean:
    """run_pytest_collect_only returns ok=True and empty failing_files on clean suite."""

    def test_returns_collect_result(self, tmp_path):
        (tmp_path / "tests").mkdir()
        clean_output = "<Module tests/test_foo.py>\n  <Function test_something>\n"
        with patch("subprocess.run", return_value=_fake_proc(0, stdout=clean_output)):
            result = run_pytest_collect_only(tmp_path)
        assert isinstance(result, CollectResult)

    def test_ok_is_true_on_clean(self, tmp_path):
        (tmp_path / "tests").mkdir()
        with patch("subprocess.run", return_value=_fake_proc(0, stdout="")):
            result = run_pytest_collect_only(tmp_path)
        assert result.ok is True

    def test_failing_files_empty_on_clean(self, tmp_path):
        (tmp_path / "tests").mkdir()
        clean_output = "<Module tests/test_foo.py>\n  <Function test_bar>\n"
        with patch("subprocess.run", return_value=_fake_proc(0, stdout=clean_output)):
            result = run_pytest_collect_only(tmp_path)
        assert result.failing_files == []

    def test_empty_suite_returns_ok(self, tmp_path):
        (tmp_path / "tests").mkdir()
        with patch("subprocess.run", return_value=_fake_proc(0, stdout="")):
            result = run_pytest_collect_only(tmp_path)
        assert result.ok is True
        assert result.failing_files == []

    def test_multiple_modules_all_clean(self, tmp_path):
        (tmp_path / "tests").mkdir()
        clean_output = (
            "<Module tests/test_a.py>\n  <Function test_x>\n"
            "<Module tests/test_b.py>\n  <Function test_y>\n"
        )
        with patch("subprocess.run", return_value=_fake_proc(0, stdout=clean_output)):
            result = run_pytest_collect_only(tmp_path)
        assert result.ok is True
        assert result.failing_files == []

    def test_missing_test_dir_returns_ok(self, tmp_path):
        # When test dir doesn't exist, returns ok=True with empty failing_files.
        result = run_pytest_collect_only(tmp_path, test_dir="tests")
        assert result.ok is True
        assert result.failing_files == []


class TestHandleCleanCollect:
    """handle_clean_collect delegates to run_pytest_collect_only and returns ok on clean."""

    def test_returns_collect_result(self, tmp_path):
        (tmp_path / "tests").mkdir()
        with patch("subprocess.run", return_value=_fake_proc(0, stdout="")):
            result = handle_clean_collect(tmp_path)
        assert isinstance(result, CollectResult)

    def test_ok_true_on_clean_suite(self, tmp_path):
        (tmp_path / "tests").mkdir()
        with patch("subprocess.run", return_value=_fake_proc(0, stdout="")):
            result = handle_clean_collect(tmp_path)
        assert result.ok is True

    def test_empty_failing_files_on_clean_suite(self, tmp_path):
        (tmp_path / "tests").mkdir()
        with patch("subprocess.run", return_value=_fake_proc(0, stdout="")):
            result = handle_clean_collect(tmp_path)
        assert result.failing_files == []

    def test_returns_not_ok_on_failure(self, tmp_path):
        (tmp_path / "tests").mkdir()
        err_output = "ERROR collecting tests/test_broken.py\nImportError: no module\n"
        with patch("subprocess.run", return_value=_fake_proc(2, stdout=err_output)):
            result = handle_clean_collect(tmp_path)
        assert result.ok is False
