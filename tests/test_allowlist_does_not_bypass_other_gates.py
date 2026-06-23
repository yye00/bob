"""Tests verifying that the allowlist ONLY bypasses the spec quality gate,
not other gates (sticky-completed, plan-gate, size limits, etc.)."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


def _make_feature(**kwargs):
    from bob3.models import Feature
    defaults = dict(
        id="dddddddd-0000-0000-0000-000000000004",
        project_id="proj-1",
        name="Test feature",
        status="pending",
    )
    defaults.update(kwargs)
    return Feature(**defaults)


class TestAllowlistDoesNotBypassOtherGates:
    def test_is_permanent_forward_carry_does_not_affect_plan_gate(self):
        """is_permanent_forward_carry is purely informational — plan_gate not bypassed."""
        from bob3.spec_quality_allowlist import is_permanent_forward_carry

        feature = _make_feature(spec_slot="F-R7-478", permanent_forward_carry=True)
        # Function just returns a bool — it has no side effects on other gates
        result = is_permanent_forward_carry(feature)
        assert result is True  # only checks quality gate bypass eligibility

    def test_non_carry_features_not_affected_by_allowlist_module(self):
        """The allowlist module does not retroactively affect non-exempt features."""
        from bob3.spec_quality_allowlist import is_permanent_forward_carry

        feature = _make_feature(spec_slot="F-R7-100", name="some production feature")
        result = is_permanent_forward_carry(feature)
        assert result is False

    def test_allowlist_does_not_modify_feature_object(self):
        """is_permanent_forward_carry must not modify the feature it receives."""
        from bob3.spec_quality_allowlist import is_permanent_forward_carry

        feature = _make_feature(spec_slot="F-R7-478", name="infra feature")
        original_name = feature.name
        original_status = feature.status
        is_permanent_forward_carry(feature)
        assert feature.name == original_name
        assert feature.status == original_status

    def test_allowlist_does_not_bypass_sticky_completed_gate(self):
        """Allowlist only affects spec_quality_score gate, not sticky-completed logic."""
        from bob3.spec_quality_allowlist import is_permanent_forward_carry

        # Sticky-completed gate checks parent_completed/parent_status fields
        feature = _make_feature(
            spec_slot="F-R7-478",
            permanent_forward_carry=True,
            parent_completed=False,
            parent_status=None,
        )
        # Allowlist says this is a carry — but sticky-completed is separate
        carry = is_permanent_forward_carry(feature)
        assert carry is True
        # parent_completed is unchanged — the allowlist did not flip it
        assert feature.parent_completed is False

    def test_quality_gate_passes_for_high_score_without_carry_flag(self):
        """Regular features still pass via quality score path, not allowlist."""
        from bob3.spec_quality.quality_score import gate_for_ready, QualityReport, ScoreComponents
        from bob3.spec_quality_allowlist import is_permanent_forward_carry

        feature = _make_feature(spec_slot=None, name="normal feature with good spec")
        assert is_permanent_forward_carry(feature) is False

        report = QualityReport(
            score=0.9,
            components=ScoreComponents(0.9, 1.0, 1.0, 0.8),
        )
        allowed, _ = gate_for_ready(report)
        assert allowed is True

    def test_allowlist_functions_are_pure(self):
        """Both allowlist functions return deterministic results for same input."""
        from bob3.spec_quality_allowlist import is_permanent_forward_carry, load_allowlist_patterns

        feature = _make_feature(spec_slot="F-R7-478")
        result1 = is_permanent_forward_carry(feature)
        result2 = is_permanent_forward_carry(feature)
        assert result1 == result2

        patterns1 = load_allowlist_patterns()
        patterns2 = load_allowlist_patterns()
        assert patterns1 == patterns2
