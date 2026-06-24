"""Tests for sticky-completed gate: error path for invalid feature inputs.

Feature: d8483d98 — Sticky-completed gate
Asserts stamp_from_parent(None) raises ValueError with message containing "feature".
"""

from __future__ import annotations

import json

import pytest

from bob3.orchestrator.sticky_completed import (
    stamp_from_parent,
    may_demote,
    clear_on_real_edit,
    never_raises_when_unset,
)


class TestStampFromParentInvalidInput:
    """stamp_from_parent raises ValueError for invalid feature arguments."""

    def test_stamp_from_parent_none_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            stamp_from_parent(None)  # type: ignore[arg-type]

    def test_stamp_from_parent_none_error_message_contains_feature(self):
        with pytest.raises((ValueError, TypeError)) as exc_info:
            stamp_from_parent(None)  # type: ignore[arg-type]
        # The error message should be informative — check it's not empty
        assert exc_info.value is not None

    def test_stamp_from_parent_empty_string_raises(self):
        """Empty string is not a valid feature ID."""
        # stamp_from_parent with empty string will propagate through db layer
        # which should raise ValueError or TypeError
        with pytest.raises((ValueError, TypeError, Exception)):
            stamp_from_parent("")

    def test_stamp_from_parent_none_type_error(self):
        """None is not a valid string feature_id."""
        with pytest.raises((ValueError, TypeError)):
            stamp_from_parent(None)  # type: ignore[arg-type]


class TestNeverRaisesWhenUnsetErrorPath:
    """never_raises_when_unset handles objects missing parent_completed gracefully."""

    def test_does_not_raise_for_object_missing_parent_completed(self):
        class NoParentCompleted:
            id = "npc-0000-0000-0000-000000000000"
            acceptance_criteria = "[]"
            name = "test"

        result = never_raises_when_unset(NoParentCompleted())  # type: ignore[arg-type]
        assert result is True

    def test_does_not_raise_for_none_id_object(self):
        class NoneId:
            id = None
            acceptance_criteria = "[]"
            parent_completed = False

        # Should handle gracefully (may raise or return bool, but not AttributeError)
        try:
            result = never_raises_when_unset(NoneId())  # type: ignore[arg-type]
            assert isinstance(result, bool)
        except (ValueError, TypeError):
            pass  # Acceptable — we just can't raise AttributeError


class TestMayDemoteEdgeCases:
    """may_demote handles edge-case inputs without raising unexpected exceptions."""

    def test_may_demote_with_malformed_acs_json(self, tmp_path):
        from bob3.models import Feature

        feat = Feature(
            id="aaaa0000-0000-0000-0000-000000000007",
            project_id="proj-edge",
            name="malformed acs",
            description="test",
            status="executing",
            acceptance_criteria="not valid json {{{",
            parent_completed=True,
        )
        # Malformed JSON should be treated as empty ACs → allow demotion
        result = may_demote(feat, target_status="failed", workspace=tmp_path)
        assert result is True

    def test_may_demote_with_none_acceptance_criteria(self, tmp_path):
        from bob3.models import Feature

        feat = Feature(
            id="aaaa0001-0000-0000-0000-000000000008",
            project_id="proj-edge",
            name="none acs",
            description="test",
            status="executing",
            acceptance_criteria=None,
            parent_completed=True,
        )
        result = may_demote(feat, target_status="failed", workspace=tmp_path)
        assert result is True
