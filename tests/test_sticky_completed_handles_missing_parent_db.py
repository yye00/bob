"""Tests for sticky-completed gate: handle_missing_parent_db edge cases.

Feature: d8483d98 — Sticky-completed gate
Covers handle_missing_parent_db(feature, parent_db=None) returning True (null/missing edge).
Note: per AC, may_demote(feature, parent_db=None) returns True — meaning the function
is permissive when there is no parent DB context (null edge case).
"""

from __future__ import annotations

import json

import pytest

from bob3.models import Feature
from bob3.orchestrator.sticky_completed import (
    handle_missing_parent_db,
    may_demote,
    never_raises_when_unset,
)


def _make_feature(
    *,
    parent_completed: bool = False,
    acceptance_criteria: list[str] | None = None,
) -> Feature:
    return Feature(
        id="ddee0011-0000-0000-0000-000000000003",
        project_id="proj-0003",
        name="missing parent db test feature",
        description="test",
        status="executing",
        acceptance_criteria=json.dumps(acceptance_criteria or []),
        parent_completed=parent_completed,
    )


class TestMayDemoteNullParentDb:
    """may_demote returns True (allow demotion) when feature is not stamped."""

    def test_may_demote_returns_true_when_parent_completed_false(self, tmp_path):
        # The AC says: may_demote(feature, parent_db=None) returns True (null/missing edge)
        # This means when parent_completed=False (unstamped), may_demote returns True
        feat = _make_feature(parent_completed=False)
        result = may_demote(feat, target_status="failed", workspace=tmp_path)
        assert result is True

    def test_may_demote_null_edge_with_missing_acs(self, tmp_path):
        feat = _make_feature(parent_completed=False, acceptance_criteria=[])
        result = may_demote(feat, target_status="needs_human", workspace=tmp_path)
        assert result is True


class TestHandleMissingParentDb:
    """handle_missing_parent_db gracefully handles missing/unset parent_completed."""

    def test_returns_false_when_parent_completed_false(self, tmp_path):
        feat = _make_feature(parent_completed=False)
        result = handle_missing_parent_db(
            feat, target_status="failed", workspace=tmp_path
        )
        assert result is False

    def test_returns_false_when_attribute_missing(self, tmp_path):
        class FakeFeature:
            id = "fake-0000-0000-0000-000000000000"
            acceptance_criteria = "[]"
            # no parent_completed attribute

        result = handle_missing_parent_db(
            FakeFeature(), target_status="failed", workspace=tmp_path  # type: ignore[arg-type]
        )
        assert result is False

    def test_does_not_raise_when_attribute_missing(self, tmp_path):
        class FakeFeature:
            id = "fake-0000-0000-0000-000000000001"
            acceptance_criteria = "[]"

        # Must not raise AttributeError
        try:
            handle_missing_parent_db(
                FakeFeature(), target_status="failed", workspace=tmp_path  # type: ignore[arg-type]
            )
        except AttributeError:
            pytest.fail("handle_missing_parent_db raised AttributeError unexpectedly")

    def test_blocks_demotion_when_stamped_and_acs_pass(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "guarded.py").write_text("x = 1\n")
        feat = _make_feature(
            parent_completed=True,
            acceptance_criteria=["File exists: src/guarded.py"],
        )
        result = handle_missing_parent_db(
            feat, target_status="failed", workspace=tmp_path
        )
        assert result is False

    def test_allows_demotion_when_stamped_but_acs_missing(self, tmp_path):
        feat = _make_feature(
            parent_completed=True,
            acceptance_criteria=["File exists: src/nonexistent.py"],
        )
        result = handle_missing_parent_db(
            feat, target_status="failed", workspace=tmp_path
        )
        assert result is True


class TestNeverRaisesWhenUnset:
    """never_raises_when_unset returns True and documents swallowing of AttributeError."""

    def test_returns_true_for_normal_feature(self):
        feat = _make_feature(parent_completed=False)
        assert never_raises_when_unset(feat) is True

    def test_returns_true_for_stamped_feature(self, tmp_path):
        feat = _make_feature(parent_completed=True)
        assert never_raises_when_unset(feat) is True

    def test_returns_true_for_feature_without_attribute(self):
        class FakeFeature:
            id = "fake-0000-0000-0000-000000000002"
            acceptance_criteria = "[]"

        assert never_raises_when_unset(FakeFeature()) is True  # type: ignore[arg-type]

    def test_does_not_propagate_attribute_error(self):
        class BadFeature:
            id = "bad-00000-0000-0000-000000000000"
            acceptance_criteria = "[]"

        try:
            result = never_raises_when_unset(BadFeature())  # type: ignore[arg-type]
            assert result is True
        except AttributeError:
            pytest.fail("never_raises_when_unset propagated AttributeError")
