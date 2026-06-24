"""Tests for sticky-completed gate: demotion always allowed when unstamped.

Feature: d8483d98 — Sticky-completed gate
Covers may_demote returning True when parent_completed=False (unstamped features).
"""

from __future__ import annotations

import json

import pytest

from bob.models import Feature
from bob.orchestrator.sticky_completed import may_demote


def _make_feature(
    *,
    parent_completed: bool = False,
    acceptance_criteria: list[str] | None = None,
) -> Feature:
    return Feature(
        id="ccddee00-0000-0000-0000-000000000002",
        project_id="proj-0002",
        name="unstamped test feature",
        description="test",
        status="executing",
        acceptance_criteria=json.dumps(acceptance_criteria or []),
        parent_completed=parent_completed,
    )


class TestMayDemoteUnstamped:
    """Unstamped features (parent_completed=False) are always demotable."""

    def test_allows_demotion_to_failed_when_unstamped(self, tmp_path):
        feat = _make_feature(parent_completed=False)
        assert may_demote(feat, target_status="failed", workspace=tmp_path) is True

    def test_allows_demotion_to_needs_human_when_unstamped(self, tmp_path):
        feat = _make_feature(parent_completed=False)
        assert may_demote(feat, target_status="needs_human", workspace=tmp_path) is True

    def test_allows_demotion_to_pending_when_unstamped(self, tmp_path):
        feat = _make_feature(parent_completed=False)
        assert may_demote(feat, target_status="pending", workspace=tmp_path) is True

    def test_allows_demotion_even_with_valid_acs_when_unstamped(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "exists.py").write_text("x = 1\n")
        feat = _make_feature(
            parent_completed=False,
            acceptance_criteria=["File exists: src/exists.py"],
        )
        # Even with ACs present and valid on disk, no stamp means demotion allowed
        assert may_demote(feat, target_status="failed", workspace=tmp_path) is True

    def test_allows_demotion_with_empty_acs_when_unstamped(self, tmp_path):
        feat = _make_feature(parent_completed=False, acceptance_criteria=[])
        assert may_demote(feat, target_status="failed", workspace=tmp_path) is True

    def test_allows_demotion_with_no_acs_kwarg_when_unstamped(self):
        feat = _make_feature(parent_completed=False)
        assert may_demote(feat, target_status="failed") is True

    def test_allows_ready_transition_when_unstamped(self, tmp_path):
        feat = _make_feature(parent_completed=False)
        assert may_demote(feat, target_status="ready", workspace=tmp_path) is True

    def test_allows_completed_transition_when_unstamped(self, tmp_path):
        feat = _make_feature(parent_completed=False)
        assert may_demote(feat, target_status="completed", workspace=tmp_path) is True
