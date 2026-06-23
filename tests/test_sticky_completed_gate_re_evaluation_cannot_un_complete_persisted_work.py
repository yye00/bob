"""Tests for sticky_completed_gate_re_evaluation_cannot_un_complete_persisted_work.

Feature: c6b09c55 — Sticky-completed gate: re-evaluation cannot un-complete
persisted work.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from bob3.models import Feature
from bob3.sticky_completed_gate_re_evaluation_cannot_un_complete_persisted_work import (
    sticky_completed_gate_re_evaluation_cannot_un_complete_persisted_work,
)


def _make_feature(
    *,
    parent_completed: bool = True,
    acceptance_criteria: list[str] | None = None,
) -> Feature:
    return Feature(
        id="c6b09c55-0000-0000-0000-000000000000",
        project_id="proj-0000",
        name="sticky gate test feature",
        description="test",
        status="executing",
        acceptance_criteria=json.dumps(acceptance_criteria or []),
        parent_completed=parent_completed,
    )


def test_sticky_completed_gate_re_evaluation_cannot_un_complete_persisted_work(
    tmp_path,
):
    """Core AC test: gate blocks demotion when parent_completed and ACs pass."""
    # Create a file satisfying the "File exists:" AC
    src = tmp_path / "src"
    src.mkdir()
    (src / "feature.py").write_text("# feature\n")

    feat = _make_feature(
        parent_completed=True,
        acceptance_criteria=["File exists: src/feature.py"],
    )

    # Gate must BLOCK demotion to 'failed' when ACs still verify on disk
    result = sticky_completed_gate_re_evaluation_cannot_un_complete_persisted_work(
        feat, target_status="failed", workspace=tmp_path
    )
    assert result is False, (
        "Sticky gate must block demotion to 'failed' when parent_completed=True "
        "and ACs still verify on disk"
    )


class TestGateAllowsDemotionWhenNotStamped:
    """Gate allows demotion when parent_completed=False."""

    def test_allows_demotion_to_failed(self, tmp_path):
        feat = _make_feature(parent_completed=False)
        result = sticky_completed_gate_re_evaluation_cannot_un_complete_persisted_work(
            feat, target_status="failed", workspace=tmp_path
        )
        assert result is True

    def test_allows_demotion_to_needs_human(self, tmp_path):
        feat = _make_feature(parent_completed=False)
        result = sticky_completed_gate_re_evaluation_cannot_un_complete_persisted_work(
            feat, target_status="needs_human", workspace=tmp_path
        )
        assert result is True

    def test_allows_demotion_to_pending(self, tmp_path):
        feat = _make_feature(parent_completed=False)
        result = sticky_completed_gate_re_evaluation_cannot_un_complete_persisted_work(
            feat, target_status="pending", workspace=tmp_path
        )
        assert result is True


class TestGateBlocksDemotionWhenAcsPass:
    """Gate blocks demotion when parent_completed and ACs verify on disk."""

    def test_blocks_failed_when_acs_pass(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "x.py").write_text("x = 1\n")
        feat = _make_feature(
            parent_completed=True,
            acceptance_criteria=["File exists: src/x.py"],
        )
        result = sticky_completed_gate_re_evaluation_cannot_un_complete_persisted_work(
            feat, target_status="failed", workspace=tmp_path
        )
        assert result is False

    def test_blocks_needs_human_when_acs_pass(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "x.py").write_text("x = 1\n")
        feat = _make_feature(
            parent_completed=True,
            acceptance_criteria=["File exists: src/x.py"],
        )
        result = sticky_completed_gate_re_evaluation_cannot_un_complete_persisted_work(
            feat, target_status="needs_human", workspace=tmp_path
        )
        assert result is False

    def test_blocks_pending_when_acs_pass(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "x.py").write_text("x = 1\n")
        feat = _make_feature(
            parent_completed=True,
            acceptance_criteria=["File exists: src/x.py"],
        )
        result = sticky_completed_gate_re_evaluation_cannot_un_complete_persisted_work(
            feat, target_status="pending", workspace=tmp_path
        )
        assert result is False


class TestGateAllowsDemotionWhenAcsFail:
    """Gate allows demotion when AC artifacts are gone from disk."""

    def test_allows_when_file_missing(self, tmp_path):
        feat = _make_feature(
            parent_completed=True,
            acceptance_criteria=["File exists: src/nonexistent.py"],
        )
        result = sticky_completed_gate_re_evaluation_cannot_un_complete_persisted_work(
            feat, target_status="failed", workspace=tmp_path
        )
        assert result is True

    def test_allows_when_no_acs(self, tmp_path):
        feat = _make_feature(
            parent_completed=True,
            acceptance_criteria=[],
        )
        result = sticky_completed_gate_re_evaluation_cannot_un_complete_persisted_work(
            feat, target_status="failed", workspace=tmp_path
        )
        assert result is True


class TestGateAllowsNonDemotingStatuses:
    """Gate never blocks non-demoting status transitions."""

    def test_allows_ready(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "x.py").write_text("x = 1\n")
        feat = _make_feature(
            parent_completed=True,
            acceptance_criteria=["File exists: src/x.py"],
        )
        result = sticky_completed_gate_re_evaluation_cannot_un_complete_persisted_work(
            feat, target_status="ready", workspace=tmp_path
        )
        assert result is True

    def test_allows_completed(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "x.py").write_text("x = 1\n")
        feat = _make_feature(
            parent_completed=True,
            acceptance_criteria=["File exists: src/x.py"],
        )
        result = sticky_completed_gate_re_evaluation_cannot_un_complete_persisted_work(
            feat, target_status="completed", workspace=tmp_path
        )
        assert result is True

    def test_allows_executing(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "x.py").write_text("x = 1\n")
        feat = _make_feature(
            parent_completed=True,
            acceptance_criteria=["File exists: src/x.py"],
        )
        result = sticky_completed_gate_re_evaluation_cannot_un_complete_persisted_work(
            feat, target_status="executing", workspace=tmp_path
        )
        assert result is True
