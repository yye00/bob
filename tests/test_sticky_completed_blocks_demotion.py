"""Tests for sticky-completed gate: may_demote blocks demotion when parent_completed=True.

Feature: eb3c74d9 — Sticky-completed gate
"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import patch

import pytest

from bob3.models import Feature
from bob3.orchestrator.sticky_completed import may_demote, stamp_from_parent, clear_stamp


def _make_feature(
    *,
    parent_completed: bool = True,
    acceptance_criteria: list[str] | None = None,
) -> Feature:
    return Feature(
        id="aabbccdd-0000-0000-0000-000000000000",
        project_id="proj-0000",
        name="test feature",
        description="test",
        status="executing",
        acceptance_criteria=json.dumps(acceptance_criteria or []),
        parent_completed=parent_completed,
    )


class TestMayDemoteWithNoStamp:
    """When parent_completed=False, demotion is always allowed."""

    def test_allows_demotion_to_failed(self):
        feat = _make_feature(parent_completed=False)
        assert may_demote(feat, target_status="failed") is True

    def test_allows_demotion_to_needs_human(self):
        feat = _make_feature(parent_completed=False)
        assert may_demote(feat, target_status="needs_human") is True

    def test_allows_demotion_to_pending(self):
        feat = _make_feature(parent_completed=False)
        assert may_demote(feat, target_status="pending") is True


class TestMayDemoteTargetAboveReady:
    """Demotion to 'ready' or 'completed' is never blocked."""

    def test_allows_ready_even_with_stamp(self):
        feat = _make_feature(parent_completed=True)
        assert may_demote(feat, target_status="ready") is True

    def test_allows_completed_even_with_stamp(self):
        feat = _make_feature(parent_completed=True)
        assert may_demote(feat, target_status="completed") is True

    def test_allows_executing_even_with_stamp(self):
        feat = _make_feature(parent_completed=True)
        assert may_demote(feat, target_status="executing") is True


class TestMayDemoteWhenAcsPass:
    """With parent_completed=True and ACs passing on disk, demotion is blocked."""

    def test_blocks_demotion_to_failed_when_acs_pass(self, tmp_path):
        # Create a real file that satisfies 'File exists:' AC
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "myfile.py").write_text("# hello\n")
        feat = _make_feature(
            parent_completed=True,
            acceptance_criteria=["File exists: src/myfile.py"],
        )
        result = may_demote(feat, target_status="failed", workspace=tmp_path)
        assert result is False

    def test_blocks_demotion_to_needs_human_when_acs_pass(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "myfile.py").write_text("# hello\n")
        feat = _make_feature(
            parent_completed=True,
            acceptance_criteria=["File exists: src/myfile.py"],
        )
        result = may_demote(feat, target_status="needs_human", workspace=tmp_path)
        assert result is False

    def test_blocks_demotion_to_pending_when_acs_pass(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "myfile.py").write_text("# hello\n")
        feat = _make_feature(
            parent_completed=True,
            acceptance_criteria=["File exists: src/myfile.py"],
        )
        result = may_demote(feat, target_status="pending", workspace=tmp_path)
        assert result is False


class TestMayDemoteWhenAcsFail:
    """With parent_completed=True but ACs failing, demotion is allowed."""

    def test_allows_demotion_when_file_missing(self, tmp_path):
        feat = _make_feature(
            parent_completed=True,
            acceptance_criteria=["File exists: src/nonexistent.py"],
        )
        result = may_demote(feat, target_status="failed", workspace=tmp_path)
        assert result is True

    def test_allows_demotion_when_no_acs(self, tmp_path):
        feat = _make_feature(
            parent_completed=True,
            acceptance_criteria=[],
        )
        result = may_demote(feat, target_status="failed", workspace=tmp_path)
        assert result is True


class TestMayDemoteDefaultWorkspace:
    """may_demote falls back to cwd when workspace=None."""

    def test_uses_cwd_when_workspace_none(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "afile.py").write_text("x = 1\n")
        feat = _make_feature(
            parent_completed=True,
            acceptance_criteria=["File exists: src/afile.py"],
        )
        # ACs pass in cwd, so gate should block
        result = may_demote(feat, target_status="failed")
        assert result is False


class TestStampFromParent:
    """stamp_from_parent calls db.update_feature with parent_completed=True."""

    def test_stamp_calls_db_update(self):
        with patch("bob3.db.update_feature") as mock_update:
            stamp_from_parent("aabbccdd-0000-0000-0000-000000000000")
            mock_update.assert_called_once_with(
                "aabbccdd-0000-0000-0000-000000000000", parent_completed=True
            )


class TestClearStamp:
    """clear_stamp calls db.update_feature with parent_completed=False."""

    def test_clear_calls_db_update(self):
        with patch("bob3.db.update_feature") as mock_update:
            clear_stamp("aabbccdd-0000-0000-0000-000000000000")
            mock_update.assert_called_once_with(
                "aabbccdd-0000-0000-0000-000000000000", parent_completed=False
            )
