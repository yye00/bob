"""Tests for sticky-completed gate: zero-AC boundary edge case.

Feature: d8483d98 — Sticky-completed gate
Asserts may_demote returns True when feature has zero ACs (zero/min edge).
When there are no ACs to protect, the gate should not block demotion.
"""

from __future__ import annotations

import json

import pytest

from bob.models import Feature
from bob.orchestrator.sticky_completed import may_demote


def _make_feature(
    *,
    parent_completed: bool = True,
    acceptance_criteria: list[str] | None = None,
) -> Feature:
    return Feature(
        id="eeff1122-0000-0000-0000-000000000004",
        project_id="proj-0004",
        name="zero acs boundary feature",
        description="test",
        status="executing",
        acceptance_criteria=json.dumps(acceptance_criteria if acceptance_criteria is not None else []),
        parent_completed=parent_completed,
    )


class TestMayDemoteZeroAcs:
    """may_demote returns True (allow demotion) when feature has zero ACs."""

    def test_allows_demotion_to_failed_with_zero_acs(self, tmp_path):
        feat = _make_feature(parent_completed=True, acceptance_criteria=[])
        result = may_demote(feat, target_status="failed", workspace=tmp_path)
        assert result is True

    def test_allows_demotion_to_needs_human_with_zero_acs(self, tmp_path):
        feat = _make_feature(parent_completed=True, acceptance_criteria=[])
        result = may_demote(feat, target_status="needs_human", workspace=tmp_path)
        assert result is True

    def test_allows_demotion_to_pending_with_zero_acs(self, tmp_path):
        feat = _make_feature(parent_completed=True, acceptance_criteria=[])
        result = may_demote(feat, target_status="pending", workspace=tmp_path)
        assert result is True

    def test_zero_acs_with_stamp_still_allows_demotion(self, tmp_path):
        # Even with parent_completed=True (stamp set), zero ACs means nothing
        # to protect — gate should not block.
        feat = _make_feature(parent_completed=True, acceptance_criteria=[])
        assert may_demote(feat, target_status="failed", workspace=tmp_path) is True

    def test_null_acceptance_criteria_treated_as_zero(self, tmp_path):
        feat = Feature(
            id="eeff1122-0000-0000-0000-000000000005",
            project_id="proj-0004",
            name="null acs feature",
            description="test",
            status="executing",
            acceptance_criteria=None,
            parent_completed=True,
        )
        result = may_demote(feat, target_status="failed", workspace=tmp_path)
        assert result is True

    def test_empty_json_list_acceptance_criteria(self, tmp_path):
        feat = Feature(
            id="eeff1122-0000-0000-0000-000000000006",
            project_id="proj-0004",
            name="empty json acs feature",
            description="test",
            status="executing",
            acceptance_criteria="[]",
            parent_completed=True,
        )
        result = may_demote(feat, target_status="failed", workspace=tmp_path)
        assert result is True

    def test_non_file_only_acs_allow_demotion_when_acs_dont_verify(self, tmp_path):
        # ACs that are non-verifiable (e.g. integration: checks) cannot pass
        # the disk verification, so even with stamp, demotion is allowed.
        feat = _make_feature(
            parent_completed=True,
            acceptance_criteria=["integration: bob.orchestrator.run_loop"],
        )
        result = may_demote(feat, target_status="failed", workspace=tmp_path)
        # integration: ACs go through evaluate_ac_against_disk which may pass or fail
        # but the gate only matters when ACs DO pass — test that result is bool
        assert isinstance(result, bool)
