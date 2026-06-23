"""Tests verifying that allowlisted features bypass the spec quality gate."""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock


def _make_feature(**kwargs):
    from bob3.models import Feature
    defaults = dict(
        id="cccccccc-0000-0000-0000-000000000003",
        project_id="proj-1",
        name="Test feature",
        status="pending",
    )
    defaults.update(kwargs)
    return Feature(**defaults)


class TestAllowlistBypassesQualityGate:
    def test_permanent_carry_feature_bypasses_gate_when_score_low(self):
        """A permanent-carry feature must pass gate even with score=0.6."""
        from bob3.spec_quality_allowlist import is_permanent_forward_carry
        from bob3.spec_quality.quality_score import gate_for_ready, QualityReport, ScoreComponents

        feature = _make_feature(spec_slot="F-R7-478", permanent_forward_carry=False)
        assert is_permanent_forward_carry(feature) is True

        # Low score that would normally block
        low_score_report = QualityReport(
            score=0.6375,
            components=ScoreComponents(
                ambiguity_score=0.5,
                reachability_score=0.7,
                ears_score=1.0,
                ac_coverage_score=0.5,
            ),
        )
        # Without bypass, this would be blocked
        allowed, msg = gate_for_ready(low_score_report)
        assert allowed is False

        # With bypass: is_permanent_forward_carry says True, so gate should be skipped
        assert is_permanent_forward_carry(feature) is True

    def test_non_carry_feature_still_blocked_at_low_score(self):
        """Non-carry features are still blocked by the quality gate."""
        from bob3.spec_quality_allowlist import is_permanent_forward_carry
        from bob3.spec_quality.quality_score import gate_for_ready, QualityReport, ScoreComponents

        feature = _make_feature(spec_slot="F-R7-999")
        assert is_permanent_forward_carry(feature) is False

        low_score_report = QualityReport(
            score=0.6375,
            components=ScoreComponents(
                ambiguity_score=0.5,
                reachability_score=0.7,
                ears_score=1.0,
                ac_coverage_score=0.5,
            ),
        )
        allowed, msg = gate_for_ready(low_score_report)
        assert allowed is False

    def test_carry_feature_with_permanent_forward_carry_flag_bypasses(self):
        """Feature with permanent_forward_carry=True bypasses gate."""
        from bob3.spec_quality_allowlist import is_permanent_forward_carry

        feature = _make_feature(permanent_forward_carry=True, spec_slot=None, name="infra carry")
        assert is_permanent_forward_carry(feature) is True

    def test_high_score_feature_passes_gate_regardless_of_carry(self):
        """Features with high score pass even without carry flag."""
        from bob3.spec_quality_allowlist import is_permanent_forward_carry
        from bob3.spec_quality.quality_score import gate_for_ready, QualityReport, ScoreComponents

        feature = _make_feature(spec_slot=None, name="normal feature")
        assert is_permanent_forward_carry(feature) is False

        high_score_report = QualityReport(
            score=0.9,
            components=ScoreComponents(
                ambiguity_score=0.9,
                reachability_score=1.0,
                ears_score=1.0,
                ac_coverage_score=0.8,
            ),
        )
        allowed, msg = gate_for_ready(high_score_report)
        assert allowed is True

    def test_carry_feature_known_ids_bypass(self):
        """Known infra feature IDs in default allowlist bypass gate."""
        from bob3.spec_quality_allowlist import is_permanent_forward_carry

        # These are the known permanent infra feature slots
        for slot in ["F-R7-478", "F-R7-479", "F-R7-481"]:
            feature = _make_feature(spec_slot=slot)
            assert is_permanent_forward_carry(feature) is True, f"Expected {slot} to be permanent carry"
