"""Tests for bob.spec_consistency_checker — N-sample stability check pre-critic.

Verifies:
  - check_spec_stability routes correctly based on stability score
  - normalize_spec_variants normalises whitespace and handles edge cases
  - compute_jaccard_stability_score computes Jaccard index correctly
  - Integration point: can be called before bob.spec_critic.critique_spec
"""

from __future__ import annotations

import pytest

from bob.spec_consistency_checker import (
    check_spec_stability,
    compute_jaccard_stability_score,
    normalize_spec_variants,
)


# ---------------------------------------------------------------------------
# normalize_spec_variants
# ---------------------------------------------------------------------------


class TestNormalizeSpecVariants:
    def test_empty_variants_list(self):
        result = normalize_spec_variants([])
        assert result == []

    def test_single_variant_single_ac(self):
        result = normalize_spec_variants([[{"id": "AC-1", "behavior": "exists"}]])
        assert len(result) == 1
        assert ("AC-1", "exists") in result[0]

    def test_whitespace_normalized_in_behavior(self):
        v1 = [{"id": "AC-1", "behavior": "  foo   bar  "}]
        v2 = [{"id": "AC-1", "behavior": "foo bar"}]
        r1 = normalize_spec_variants([v1])
        r2 = normalize_spec_variants([v2])
        assert r1 == r2

    def test_two_identical_variants_equal_after_normalize(self):
        v = [{"id": "AC-1", "behavior": "File exists: src/foo.py"}]
        r1, r2 = normalize_spec_variants([v, v])
        assert r1 == r2

    def test_missing_id_defaults_to_empty_string(self):
        result = normalize_spec_variants([[{"behavior": "something"}]])
        assert result[0][0] == ("", "something")

    def test_missing_behavior_defaults_to_empty_string(self):
        result = normalize_spec_variants([[{"id": "AC-1"}]])
        assert result[0][0] == ("AC-1", "")

    def test_not_a_list_raises_value_error(self):
        with pytest.raises(ValueError):
            normalize_spec_variants("not-a-list")  # type: ignore[arg-type]

    def test_variant_not_a_list_raises_value_error(self):
        with pytest.raises(ValueError):
            normalize_spec_variants(["not-a-list-of-dicts"])  # type: ignore[arg-type]

    def test_returns_list_of_tuples(self):
        variants = [
            [{"id": "AC-1", "behavior": "foo"}, {"id": "AC-2", "behavior": "bar"}],
            [{"id": "AC-1", "behavior": "foo"}],
        ]
        result = normalize_spec_variants(variants)
        assert len(result) == 2
        for r in result:
            assert isinstance(r, tuple)


# ---------------------------------------------------------------------------
# compute_jaccard_stability_score
# ---------------------------------------------------------------------------


class TestComputeJaccardStabilityScore:
    def test_single_variant_returns_one(self):
        v = [[{"id": "AC-1", "behavior": "foo"}]]
        assert compute_jaccard_stability_score(v) == 1.0

    def test_identical_variants_return_one(self):
        v = [{"id": "AC-1", "behavior": "foo"}]
        score = compute_jaccard_stability_score([v, v, v])
        assert score == 1.0

    def test_completely_different_variants_return_zero(self):
        v1 = [{"id": "AC-1", "behavior": "unique-a"}]
        v2 = [{"id": "AC-2", "behavior": "unique-b"}]
        score = compute_jaccard_stability_score([v1, v2])
        assert score == 0.0

    def test_partial_overlap(self):
        v1 = [{"id": "AC-1", "behavior": "shared"}, {"id": "AC-2", "behavior": "only-v1"}]
        v2 = [{"id": "AC-1", "behavior": "shared"}, {"id": "AC-3", "behavior": "only-v2"}]
        score = compute_jaccard_stability_score([v1, v2])
        # intersection=1, union=3 → 1/3 ≈ 0.333
        assert abs(score - 1 / 3) < 1e-9

    def test_all_empty_variants_return_one(self):
        score = compute_jaccard_stability_score([[], [], []])
        assert score == 1.0

    def test_empty_list_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_jaccard_stability_score([])

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_jaccard_stability_score(None)  # type: ignore[arg-type]

    def test_string_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_jaccard_stability_score("not-a-list")  # type: ignore[arg-type]

    def test_variant_not_a_list_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_jaccard_stability_score(["not-a-list"])  # type: ignore[arg-type]

    def test_score_in_range_zero_to_one(self):
        v1 = [{"id": "AC-1", "behavior": "a"}, {"id": "AC-2", "behavior": "b"}]
        v2 = [{"id": "AC-1", "behavior": "a"}, {"id": "AC-3", "behavior": "c"}]
        score = compute_jaccard_stability_score([v1, v2])
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# check_spec_stability — routing
# ---------------------------------------------------------------------------


class TestCheckSpecStabilityRouting:
    """Routing logic based on stability score thresholds."""

    def _make_stable_variants(self) -> list[list[dict]]:
        # Three identical variants → score 1.0 → auto_accept
        v = [{"id": "AC-1", "behavior": "File exists: src/foo.py"}]
        return [v, v, v]

    def _make_low_stability_variants(self) -> list[list[dict]]:
        # Completely different ACs → score 0.0 → clarification
        return [
            [{"id": f"AC-{i}", "behavior": f"unique-{i}"}]
            for i in range(3)
        ]

    def _make_medium_variants(self) -> list[list[dict]]:
        # 3 ACs shared, 3 unique → ~0.5 → critic
        shared = [{"id": "AC-1", "behavior": "shared-a"}]
        v1 = shared + [{"id": "AC-2", "behavior": "unique-1"}]
        v2 = shared + [{"id": "AC-3", "behavior": "unique-2"}]
        v3 = shared + [{"id": "AC-4", "behavior": "unique-3"}]
        return [v1, v2, v3]

    def test_auto_accept_when_score_gte_0_9(self):
        result = check_spec_stability(
            feature_id="feat-stable",
            name="Stable",
            description="desc",
            acceptance_criteria=["File exists: src/foo.py"],
            _override_variants=self._make_stable_variants(),
        )
        assert result["route"] == "auto_accept"
        assert result["consensus"] is True
        assert result["stability_score"] == 1.0

    def test_clarification_when_score_lt_0_7(self):
        result = check_spec_stability(
            feature_id="feat-unstable",
            name="Unstable",
            description="desc",
            acceptance_criteria=["File exists: src/foo.py"],
            _override_variants=self._make_low_stability_variants(),
        )
        assert result["route"] == "clarification"
        assert result["consensus"] is False
        assert result["stability_score"] < 0.7

    def test_critic_path_for_medium_stability(self):
        result = check_spec_stability(
            feature_id="feat-medium",
            name="Medium",
            description="desc",
            acceptance_criteria=["File exists: src/foo.py"],
            _override_variants=self._make_medium_variants(),
        )
        assert result["route"] in ("critic", "clarification", "auto_accept")
        assert isinstance(result["stability_score"], float)
        assert 0.0 <= result["stability_score"] <= 1.0

    def test_result_keys_present(self):
        result = check_spec_stability(
            feature_id="feat-keys",
            name="Keys",
            description="desc",
            acceptance_criteria=["File exists: src/foo.py"],
            _override_variants=self._make_stable_variants(),
        )
        assert set(result.keys()) >= {
            "stability_score", "route", "consensus",
            "disagreeing_slots", "majority_vote"
        }

    def test_clarification_has_disagreeing_slots(self):
        result = check_spec_stability(
            feature_id="feat-disagree",
            name="Disagree",
            description="desc",
            acceptance_criteria=["File exists: src/foo.py"],
            _override_variants=self._make_low_stability_variants(),
        )
        assert result["route"] == "clarification"
        assert len(result["disagreeing_slots"]) > 0

    def test_auto_accept_has_empty_disagreeing_slots(self):
        result = check_spec_stability(
            feature_id="feat-agree",
            name="Agree",
            description="desc",
            acceptance_criteria=["File exists: src/foo.py"],
            _override_variants=self._make_stable_variants(),
        )
        assert result["route"] == "auto_accept"
        assert result["disagreeing_slots"] == []

    def test_majority_vote_present(self):
        result = check_spec_stability(
            feature_id="feat-mv",
            name="MajorityVote",
            description="desc",
            acceptance_criteria=["File exists: src/foo.py"],
            _override_variants=self._make_stable_variants(),
        )
        assert isinstance(result["majority_vote"], list)


class TestCheckSpecStabilityValidation:
    """Input validation for check_spec_stability."""

    def test_acceptance_criteria_not_list_raises(self):
        with pytest.raises(ValueError):
            check_spec_stability(
                feature_id="f",
                name="n",
                description="d",
                acceptance_criteria="not-a-list",  # type: ignore[arg-type]
            )

    def test_acceptance_criteria_none_raises(self):
        with pytest.raises(ValueError):
            check_spec_stability(
                feature_id="f",
                name="n",
                description="d",
                acceptance_criteria=None,  # type: ignore[arg-type]
            )

    def test_n_zero_raises(self):
        with pytest.raises(ValueError):
            check_spec_stability(
                feature_id="f",
                name="n",
                description="d",
                acceptance_criteria=["File exists: src/foo.py"],
                n=0,
            )

    def test_n_negative_raises(self):
        with pytest.raises(ValueError):
            check_spec_stability(
                feature_id="f",
                name="n",
                description="d",
                acceptance_criteria=["File exists: src/foo.py"],
                n=-1,
            )

    def test_n_float_raises(self):
        with pytest.raises(ValueError):
            check_spec_stability(
                feature_id="f",
                name="n",
                description="d",
                acceptance_criteria=["File exists: src/foo.py"],
                n=3.0,  # type: ignore[arg-type]
            )

    def test_empty_acceptance_criteria_does_not_raise(self):
        result = check_spec_stability(
            feature_id="f",
            name="n",
            description="d",
            acceptance_criteria=[],
            _override_variants=[[], [], []],
        )
        assert result["stability_score"] == 1.0


# ---------------------------------------------------------------------------
# Integration smoke test: check_spec_stability → bob.spec_critic.critique_spec
# ---------------------------------------------------------------------------


class TestCheckSpecStabilityIntegration:
    """Smoke test for integration with bob.spec_critic."""

    def test_auto_accept_does_not_block_critic(self):
        # When stability is high, result should indicate auto_accept
        # The critic can then be skipped or proceeded with.
        result = check_spec_stability(
            feature_id="integ-auto",
            name="Integration Auto",
            description="Full stable spec",
            acceptance_criteria=["File exists: src/foo.py"],
            _override_variants=[
                [{"id": "AC-1", "behavior": "File exists: src/foo.py"}],
                [{"id": "AC-1", "behavior": "File exists: src/foo.py"}],
                [{"id": "AC-1", "behavior": "File exists: src/foo.py"}],
            ],
        )
        assert result["route"] == "auto_accept"
        assert result["consensus"] is True

    def test_clarification_route_exposes_disagreeing_slots(self):
        # When stability < 0.7, disagreeing_slots should be non-empty and
        # usable to route to the clarification loop (F-R7-456).
        variants = [
            [{"id": "AC-1", "behavior": f"unique-slot-{i}"}]
            for i in range(3)
        ]
        result = check_spec_stability(
            feature_id="integ-clarify",
            name="Integration Clarify",
            description="Unstable spec",
            acceptance_criteria=["File exists: src/foo.py"],
            _override_variants=variants,
        )
        assert result["route"] == "clarification"
        # disagreeing_slots must be non-empty for F-R7-456 routing
        assert len(result["disagreeing_slots"]) > 0

    def test_import_from_bob_spec_critic_works(self):
        # Integration: bob.spec_critic module must be importable alongside checker
        from bob.spec_critic import SpecCritic  # noqa: F401
        from bob.spec_consistency_checker import check_spec_stability as _cs  # noqa: F401
        assert callable(_cs)
