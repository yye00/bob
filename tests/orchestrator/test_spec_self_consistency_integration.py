"""Orchestrator integration test for spec self-consistency stability check.

Verifies that the self-consistency module integrates cleanly with the orchestrator
package — both the bob.spec_quality.self_consistency module and the
bob.spec_self_consistency_n_sample_stability_check_pre_critic facade are
importable and callable from the orchestrator context.

AC: integration: tests.orchestrator (feature ca9b0c7f)
"""

from __future__ import annotations

import pytest

from bob.spec_quality.self_consistency import (
    SelfConsistencyResult,
    jaccard_stability,
    run_n_samples,
    _route_result,
    CLARIFICATION_THRESHOLD,
    AUTO_ACCEPT_THRESHOLD,
)
from bob.spec_self_consistency_n_sample_stability_check_pre_critic import (
    spec_self_consistency_n_sample_stability_check_pre_critic,
)


class TestSelfConsistencyOrchestratorIntegration:
    """Integration tests: self-consistency callable from orchestrator context."""

    def test_facade_importable(self):
        # Verifies the public facade is importable in orchestrator context
        assert callable(spec_self_consistency_n_sample_stability_check_pre_critic)

    def test_facade_returns_dict_with_required_keys(self):
        result = spec_self_consistency_n_sample_stability_check_pre_critic(
            feature_id="orch-integration-test",
            name="Orchestrator Integration Test",
            description="Integration test from tests.orchestrator",
            acceptance_criteria=[
                "File exists: src/bob/spec_quality/self_consistency.py",
                "Function defined: bob.spec_quality.self_consistency.run_n_samples",
            ],
            n=1,
        )
        assert isinstance(result, dict)
        assert "stability_score" in result
        assert "route" in result
        assert "consensus" in result
        assert "disagreeing_slots" in result
        assert "majority_vote" in result

    def test_facade_with_override_variants_high_stability(self):
        # Override variants with identical ACs → score=1.0 → auto_accept
        v = [[{"id": "AC-1", "behavior": "File exists: src/foo.py"}]] * 3
        result = spec_self_consistency_n_sample_stability_check_pre_critic(
            feature_id="orch-high-stability",
            name="High Stability",
            description="All variants identical",
            acceptance_criteria=["File exists: src/foo.py"],
            _override_variants=v,
        )
        assert result["stability_score"] == 1.0
        assert result["route"] == "auto_accept"
        assert result["consensus"] is True

    def test_facade_with_override_variants_low_stability(self):
        # Override variants with fully disjoint ACs → score=0.0 → clarification
        v1 = [{"id": "AC-1", "behavior": "alpha unique"}]
        v2 = [{"id": "AC-1", "behavior": "beta unique"}]
        v3 = [{"id": "AC-1", "behavior": "gamma unique"}]
        result = spec_self_consistency_n_sample_stability_check_pre_critic(
            feature_id="orch-low-stability",
            name="Low Stability",
            description="All variants different",
            acceptance_criteria=["placeholder"],
            _override_variants=[v1, v2, v3],
        )
        assert result["stability_score"] < CLARIFICATION_THRESHOLD
        assert result["route"] == "clarification"
        assert result["consensus"] is False
        assert len(result["disagreeing_slots"]) > 0

    def test_jaccard_stability_importable_from_core(self):
        # Core Jaccard function is importable
        score = jaccard_stability([
            [{"id": "AC-1", "behavior": "same"}],
            [{"id": "AC-1", "behavior": "same"}],
        ])
        assert score == 1.0

    def test_thresholds_have_expected_values(self):
        assert CLARIFICATION_THRESHOLD == 0.7
        assert AUTO_ACCEPT_THRESHOLD == 0.9

    def test_run_n_samples_importable(self):
        assert callable(run_n_samples)

    def test_route_result_importable(self):
        assert callable(_route_result)
