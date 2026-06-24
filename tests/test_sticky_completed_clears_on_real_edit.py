"""Tests for sticky-completed gate: stamp clears after real edits.

Feature: eb3c74d9 — Sticky-completed gate
Covers ac_files_modified detecting real writes and clear_stamp resetting the guard.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import time
from unittest.mock import patch

import pytest

from bob.models import Feature
from bob.orchestrator.sticky_completed import ac_files_modified, clear_stamp


def _make_feature(acceptance_criteria: list[str]) -> Feature:
    return Feature(
        id="aabbccdd-0000-0000-0000-000000000001",
        project_id="proj-0001",
        name="ac-mod test feature",
        description="test",
        status="executing",
        acceptance_criteria=json.dumps(acceptance_criteria),
        parent_completed=True,
    )


class TestAcFilesModifiedGit:
    """ac_files_modified uses git diff when workspace is a git repo."""

    def _init_git_repo(self, path: pathlib.Path) -> None:
        subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(path), check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(path), check=True, capture_output=True,
        )

    def _commit_file(self, path: pathlib.Path, rel: str, content: str) -> None:
        p = path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        subprocess.run(["git", "add", rel], cwd=str(path), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(path), check=True, capture_output=True,
        )

    def test_detects_modified_ac_file_via_git(self, tmp_path):
        self._init_git_repo(tmp_path)
        self._commit_file(tmp_path, "src/foo.py", "# original\n")
        # Write a second commit that changes the file
        (tmp_path / "src" / "foo.py").write_text("# changed\n")
        subprocess.run(
            ["git", "add", "src/foo.py"],
            cwd=str(tmp_path), check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "edit"],
            cwd=str(tmp_path), check=True, capture_output=True,
        )

        feat = _make_feature(["File exists: src/foo.py"])
        assert ac_files_modified(feat, workspace=tmp_path) is True

    def test_no_modification_returns_false_via_git(self, tmp_path):
        self._init_git_repo(tmp_path)
        self._commit_file(tmp_path, "src/bar.py", "# v1\n")
        # Second commit only touches an unrelated file
        (tmp_path / "other.txt").write_text("unrelated\n")
        subprocess.run(["git", "add", "other.txt"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "other"],
            cwd=str(tmp_path), check=True, capture_output=True,
        )

        feat = _make_feature(["File exists: src/bar.py"])
        assert ac_files_modified(feat, workspace=tmp_path) is False


class TestAcFilesModifiedMtime:
    """ac_files_modified falls back to mtime when git unavailable."""

    def test_detects_modification_via_mtime(self, tmp_path, monkeypatch):
        # Patch subprocess.run to simulate git failure so mtime path is used
        import subprocess as sp

        orig_run = sp.run

        def fake_run(cmd, *args, **kwargs):
            if cmd[0] == "git":
                class R:
                    returncode = 1
                    stdout = ""
                    stderr = ""
                return R()
            return orig_run(cmd, *args, **kwargs)

        monkeypatch.setattr(sp, "run", fake_run)

        (tmp_path / "src").mkdir()
        target = tmp_path / "src" / "thing.py"
        target.write_text("x = 1\n")
        # since_mtime is in the past relative to the file
        since = target.stat().st_mtime - 1.0

        feat = _make_feature(["File exists: src/thing.py"])
        assert ac_files_modified(feat, workspace=tmp_path, since_mtime=since) is True

    def test_no_modification_via_mtime_when_old(self, tmp_path, monkeypatch):
        import subprocess as sp

        orig_run = sp.run

        def fake_run(cmd, *args, **kwargs):
            if cmd[0] == "git":
                class R:
                    returncode = 1
                    stdout = ""
                    stderr = ""
                return R()
            return orig_run(cmd, *args, **kwargs)

        monkeypatch.setattr(sp, "run", fake_run)

        (tmp_path / "src").mkdir()
        target = tmp_path / "src" / "thing2.py"
        target.write_text("y = 2\n")
        # since_mtime is in the future relative to the file
        since = target.stat().st_mtime + 100.0

        feat = _make_feature(["File exists: src/thing2.py"])
        assert ac_files_modified(feat, workspace=tmp_path, since_mtime=since) is False


class TestAcFilesModifiedNoAcs:
    """ac_files_modified returns False when no parseable file paths in ACs."""

    def test_no_file_acs_returns_false(self, tmp_path):
        feat = _make_feature(["integration: bob.orchestrator.run_loop"])
        assert ac_files_modified(feat, workspace=tmp_path) is False

    def test_empty_acs_returns_false(self, tmp_path):
        feat = _make_feature([])
        assert ac_files_modified(feat, workspace=tmp_path) is False


class TestAcFilesModifiedPytestPaths:
    """ac_files_modified extracts test file paths from pytest: ACs."""

    def test_detects_modification_of_pytest_test_file(self, tmp_path, monkeypatch):
        import subprocess as sp

        orig_run = sp.run

        def fake_run(cmd, *args, **kwargs):
            if cmd[0] == "git":
                class R:
                    returncode = 1
                    stdout = ""
                    stderr = ""
                return R()
            return orig_run(cmd, *args, **kwargs)

        monkeypatch.setattr(sp, "run", fake_run)

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_thing.py"
        test_file.write_text("def test_a(): assert True\n")
        since = test_file.stat().st_mtime - 1.0

        feat = _make_feature(["pytest: tests/test_thing.py"])
        assert ac_files_modified(feat, workspace=tmp_path, since_mtime=since) is True


class TestClearStampIntegration:
    """clear_stamp resets the parent_completed field via db."""

    def test_clear_stamp_calls_update(self):
        with patch("bob.db.update_feature") as mock_update:
            clear_stamp("aabbccdd-0000-0000-0000-000000000001")
            mock_update.assert_called_once_with(
                "aabbccdd-0000-0000-0000-000000000001", parent_completed=False
            )
