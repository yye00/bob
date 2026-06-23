"""Tests error path: emit_rtm_json raises PermissionError when runs/ dir not writable."""

from __future__ import annotations

import os
import pathlib
import stat

import pytest


@pytest.fixture()
def minimal_rtm() -> dict:
    return {
        "feature_id": "feat-perm-test",
        "acs": {},
        "spec_coverage_pct": 1.0,
        "untraced_implementations": [],
    }


def test_emit_rtm_json_raises_permission_error_on_unwritable_dir(tmp_path, minimal_rtm):
    from tools.spec_coverage import emit_rtm_json

    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    runs_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # read+execute only, no write

    try:
        with pytest.raises(PermissionError) as exc_info:
            emit_rtm_json(minimal_rtm, runs_dir=runs_dir, feature_id="feat-perm-test")

        assert "permission" in str(exc_info.value).lower()
    finally:
        runs_dir.chmod(stat.S_IRWXU)


def test_emit_rtm_json_permission_error_message_contains_permission(tmp_path, minimal_rtm):
    """Error message must contain 'permission' (case-insensitive)."""
    from tools.spec_coverage import emit_rtm_json

    runs_dir = tmp_path / "locked_runs"
    runs_dir.mkdir()
    runs_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)

    try:
        with pytest.raises(PermissionError) as exc_info:
            emit_rtm_json(minimal_rtm, runs_dir=runs_dir, feature_id="feat-msg")

        error_msg = str(exc_info.value).lower()
        assert "permission" in error_msg, (
            f"Expected 'permission' in error message, got: {exc_info.value}"
        )
    finally:
        runs_dir.chmod(stat.S_IRWXU)


@pytest.mark.skipif(os.getuid() == 0, reason="Root bypasses file permission checks")
def test_emit_rtm_json_not_osserror_but_permission_error(tmp_path, minimal_rtm):
    """Must raise PermissionError specifically (subclass of OSError)."""
    from tools.spec_coverage import emit_rtm_json

    runs_dir = tmp_path / "no_write"
    runs_dir.mkdir()
    runs_dir.chmod(0o500)

    try:
        with pytest.raises(PermissionError):
            emit_rtm_json(minimal_rtm, runs_dir=runs_dir, feature_id="feat-type")
    finally:
        runs_dir.chmod(0o700)
