"""Tests for hippy.spec_self_consistency (feature f67017b4).

ACs:
  - File exists: src/hippy/spec_self_consistency.py
  - Function defined: hippy.spec_self_consistency.compute_stability_score
  - Function defined: hippy.spec_self_consistency.run_self_consistency_check
  - integration: hippy.spec_extractor
"""

from __future__ import annotations

import pytest

from hippy.spec_self_consistency import (
    SelfConsistencyResult,
    compute_stability_score,
    run_self_consistency_check,
)


class TestComputeStabilityScore:
    def test_single_variant_returns_one(self):
        assert compute_stability_score([[{"id": "AC-1", "behavior": "foo"}]]) == pytest.approx(1.0)

    def test_identical_variants_return_one(self):
        ac = [{"id": "AC-1", "behavior": "file exists"}]
        assert compute_stability_score([ac, ac, ac]) == pytest.approx(1.0)

    def test_disjoint_variants_return_zero(self):
        variants = [
            [{"id": "AC-1", "behavior": "alpha"}],
            [{"id": "AC-2", "behavior": "beta"}],
        ]
        assert compute_stability_score(variants) == pytest.approx(0.0)

    def test_partial_overlap(self):
        variants = [
            [{"id": "AC-1", "behavior": "shared"}, {"id": "AC-2", "behavior": "a"}],
            [{"id": "AC-1", "behavior": "shared"}, {"id": "AC-3", "behavior": "b"}],
        ]
        assert compute_stability_score(variants) == pytest.approx(1 / 3, abs=1e-6)

    def test_score_is_float_in_range(self):
        score = compute_stability_score([[{"id": "AC-1", "behavior": "x"}]])
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_empty_variants_each_empty_returns_one(self):
        assert compute_stability_score([[], []]) == pytest.approx(1.0)

    # --- error path ---
    def test_empty_list_raises(self):
        with pytest.raises(ValueError):
            compute_stability_score([])

    def test_none_raises(self):
        with pytest.raises(ValueError):
            compute_stability_score(None)  # type: ignore[arg-type]

    def test_non_list_raises(self):
        with pytest.raises(ValueError):
            compute_stability_score("nope")  # type: ignore[arg-type]

    def test_variant_not_a_list_raises(self):
        with pytest.raises(ValueError):
            compute_stability_score([42])  # type: ignore[arg-type]


class TestRunSelfConsistencyCheck:
    def test_returns_result(self, tmp_path):
        result = run_self_consistency_check(
            feature_id="f-1",
            name="Test",
            description="desc",
            acceptance_criteria=["File exists: src/foo.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert isinstance(result, SelfConsistencyResult)

    def test_score_in_range_and_valid_route(self, tmp_path):
        result = run_self_consistency_check(
            feature_id="f-2",
            name="Test",
            description="desc",
            acceptance_criteria=["pytest: tests/test_x.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert 0.0 <= result.stability_score <= 1.0
        assert result.route in ("clarification", "critic", "auto_accept")
        assert isinstance(result.consensus, bool)

    def test_n1_is_auto_accept(self, tmp_path):
        result = run_self_consistency_check(
            feature_id="f-3",
            name="Test",
            description="desc",
            acceptance_criteria=["File exists: src/x.py"],
            n=1,
            variants_dir=tmp_path,
        )
        assert result.stability_score == pytest.approx(1.0)
        assert result.route == "auto_accept"
        assert result.consensus is True

    def test_consensus_only_for_auto_accept(self, tmp_path):
        result = run_self_consistency_check(
            feature_id="f-4",
            name="Test",
            description="desc",
            acceptance_criteria=["File exists: src/x.py"],
            n=3,
            variants_dir=tmp_path,
        )
        if result.route == "auto_accept":
            assert result.consensus is True
        else:
            assert result.consensus is False

    def test_persists_variants_yaml(self, tmp_path):
        run_self_consistency_check(
            feature_id="f-5",
            name="Test",
            description="desc",
            acceptance_criteria=["File exists: src/x.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert (tmp_path / "f-5" / "variants.yaml").exists()

    def test_empty_acceptance_criteria_returns_result(self, tmp_path):
        result = run_self_consistency_check(
            feature_id="f-6",
            name="Test",
            description="desc",
            acceptance_criteria=[],
            n=3,
            variants_dir=tmp_path,
        )
        assert result.stability_score == pytest.approx(1.0)
        assert result.route == "auto_accept"

    # --- error path ---
    def test_bad_acceptance_criteria_raises(self, tmp_path):
        with pytest.raises(ValueError):
            run_self_consistency_check(
                feature_id="f-e",
                name="Test",
                description="desc",
                acceptance_criteria="not-a-list",  # type: ignore[arg-type]
                variants_dir=tmp_path,
            )

    def test_n_zero_raises(self, tmp_path):
        with pytest.raises(ValueError):
            run_self_consistency_check(
                feature_id="f-e",
                name="Test",
                description="desc",
                acceptance_criteria=["File exists: src/x.py"],
                n=0,
                variants_dir=tmp_path,
            )

    def test_n_float_raises(self, tmp_path):
        with pytest.raises(ValueError):
            run_self_consistency_check(
                feature_id="f-e",
                name="Test",
                description="desc",
                acceptance_criteria=["File exists: src/x.py"],
                n=3.0,  # type: ignore[arg-type]
                variants_dir=tmp_path,
            )


class TestIntegrationSpecExtractor:
    def test_spec_extractor_importable(self):
        import hippy.spec_extractor as se

        assert hasattr(se, "extract_variant")

    def test_extract_variant_returns_ac_list(self):
        from hippy.spec_extractor import extract_variant

        variant = extract_variant(
            feature_id="f-i",
            name="Test",
            description="desc",
            acceptance_criteria=["File exists: src/foo.py"],
            seed=0,
        )
        assert isinstance(variant, list)
        assert variant and set(variant[0].keys()) >= {"id", "behavior"}

    def test_check_uses_extractor(self, tmp_path):
        # run_self_consistency_check integrates hippy.spec_extractor
        result = run_self_consistency_check(
            feature_id="f-int",
            name="Test",
            description="desc",
            acceptance_criteria=["File exists: src/a.py", "pytest: tests/test_a.py"],
            n=3,
            variants_dir=tmp_path,
        )
        assert isinstance(result.majority_vote, list)
        assert isinstance(result.disagreeing_slots, list)
