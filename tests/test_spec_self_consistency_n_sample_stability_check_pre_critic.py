"""Tests for spec_self_consistency_n_sample_stability_check_pre_critic."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob.spec_self_consistency_n_sample_stability_check_pre_critic import (
    spec_self_consistency_n_sample_stability_check_pre_critic,
)


def test_spec_self_consistency_n_sample_stability_check_pre_critic():
    """Core AC test: function exists and runs N-sample stability check pre-critic."""
    result = spec_self_consistency_n_sample_stability_check_pre_critic(
        feature_id="test-feature-001",
        name="Test Feature",
        description="A test feature for validation.",
        acceptance_criteria=[
            "File exists: src/bob/foo.py",
            "pytest: tests/test_foo.py::test_foo",
            "Function defined: bob.foo.foo",
        ],
        n=3,
    )

    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert "stability_score" in result, "Result must contain 'stability_score'"
    assert "route" in result, "Result must contain 'route'"
    assert "consensus" in result, "Result must contain 'consensus'"
    assert "disagreeing_slots" in result, "Result must contain 'disagreeing_slots'"
    assert "majority_vote" in result, "Result must contain 'majority_vote'"

    score = result["stability_score"]
    assert isinstance(score, float), f"stability_score must be float, got {type(score)}"
    assert 0.0 <= score <= 1.0, f"stability_score {score} not in [0, 1]"

    route = result["route"]
    assert route in ("clarification", "critic", "auto_accept"), (
        f"Unexpected route: {route!r}"
    )

    assert isinstance(result["consensus"], bool), "consensus must be bool"
    assert isinstance(result["disagreeing_slots"], list), "disagreeing_slots must be list"
    assert isinstance(result["majority_vote"], list), "majority_vote must be list"


def test_high_stability_routes_to_auto_accept():
    """Identical ACs across all N samples produce score=1.0 → route=auto_accept, consensus=True."""
    result = spec_self_consistency_n_sample_stability_check_pre_critic(
        feature_id="test-high-stable",
        name="Stable Feature",
        description="Feature with stable ACs.",
        acceptance_criteria=[
            "File exists: src/bob/stable.py",
        ],
        n=1,
    )
    assert result["stability_score"] == pytest.approx(1.0, abs=1e-9)
    assert result["route"] == "auto_accept"
    assert result["consensus"] is True
    assert result["disagreeing_slots"] == []


def test_stability_score_below_clarification_threshold_routes_to_clarification():
    """score < 0.7 routes to 'clarification' with disagreeing_slots cited."""
    from bob.spec_quality.self_consistency import (
        CLARIFICATION_THRESHOLD,
        jaccard_stability,
        run_n_samples,
    )

    variants = [
        [{"id": "AC-1", "behavior": "behavior A"}],
        [{"id": "AC-1", "behavior": "behavior B"}],
        [{"id": "AC-1", "behavior": "behavior C"}],
    ]
    score = jaccard_stability(variants)
    assert score < CLARIFICATION_THRESHOLD, (
        f"Expected score < {CLARIFICATION_THRESHOLD}, got {score}"
    )

    result = spec_self_consistency_n_sample_stability_check_pre_critic(
        feature_id="test-low-stable",
        name="Unstable Feature",
        description="Feature with wildly varying ACs.",
        acceptance_criteria=[
            "File exists: src/a.py",
            "pytest: tests/test_a.py::test_a_one",
            "pytest: tests/test_a.py::test_a_two",
            "pytest: tests/test_a.py::test_a_three",
            "pytest: tests/test_a.py::test_a_four",
        ],
        n=3,
        _override_variants=variants,
    )
    assert result["route"] == "clarification"
    assert result["consensus"] is False
    assert len(result["disagreeing_slots"]) > 0


def test_stability_score_at_auto_accept_threshold():
    """score >= 0.9 routes to 'auto_accept' with consensus=True."""
    variants = [
        [{"id": "AC-1", "behavior": "file exists"}, {"id": "AC-2", "behavior": "test passes"}],
        [{"id": "AC-1", "behavior": "file exists"}, {"id": "AC-2", "behavior": "test passes"}],
        [{"id": "AC-1", "behavior": "file exists"}, {"id": "AC-2", "behavior": "test passes"}],
    ]

    result = spec_self_consistency_n_sample_stability_check_pre_critic(
        feature_id="test-auto-accept",
        name="Very Stable Feature",
        description="Feature with perfect stability.",
        acceptance_criteria=[
            "File exists: src/bob/stable.py",
            "pytest: tests/test_stable.py::test_stable",
        ],
        n=3,
        _override_variants=variants,
    )
    assert result["stability_score"] == pytest.approx(1.0, abs=1e-9)
    assert result["route"] == "auto_accept"
    assert result["consensus"] is True


def test_n_default_is_3():
    """Default n=3 runs 3 samples."""
    result = spec_self_consistency_n_sample_stability_check_pre_critic(
        feature_id="test-default-n",
        name="Default N Feature",
        description="Feature using default n=3.",
        acceptance_criteria=["File exists: src/bob/x.py"],
    )
    assert isinstance(result, dict)
    assert "stability_score" in result


def test_majority_vote_is_non_empty_for_auto_accept():
    """Auto-accept results include a non-empty majority_vote."""
    result = spec_self_consistency_n_sample_stability_check_pre_critic(
        feature_id="test-majority-vote",
        name="Vote Feature",
        description="Test majority vote.",
        acceptance_criteria=["File exists: src/bob/mv.py"],
        n=1,
    )
    assert result["route"] == "auto_accept"
    assert len(result["majority_vote"]) > 0


def test_result_contains_consensus_true_for_auto_accept():
    """Consensus flag is True only for auto_accept route."""
    result = spec_self_consistency_n_sample_stability_check_pre_critic(
        feature_id="test-consensus",
        name="Consensus Feature",
        description="Test consensus.",
        acceptance_criteria=["File exists: src/bob/c.py"],
        n=1,
    )
    if result["route"] == "auto_accept":
        assert result["consensus"] is True
    else:
        assert result["consensus"] is False
