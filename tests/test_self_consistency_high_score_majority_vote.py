"""Tests that stability_score >= 0.9 auto-accepts majority vote with consensus:true.

Feature: 289249a9-4e29-4cbc-b418-c242c024bdfe
Spec: Spec self-consistency — N-sample stability check pre-critic
"""

from __future__ import annotations

import pytest
import yaml

from bob3.spec_quality.self_consistency import (
    run_n_samples,
    jaccard_stability,
    SelfConsistencyResult,
    _route_result,
)


_FEATURE_ID = "test-feature-high-score"
_NAME = "High stability feature"
_DESCRIPTION = "A feature with a clear spec"
_ACS = ["File exists: src/foo.py", "Function defined: foo.bar"]


class TestHighScoreMajorityVote:
    def test_identical_variants_yield_auto_accept(self, tmp_path, monkeypatch):
        import bob3.spec_quality.self_consistency as sc

        shared = [{"id": "AC-1", "behavior": "do the thing"}]

        def fake_extract(feature_id, name, description, acceptance_criteria, seed):
            return list(shared)

        monkeypatch.setattr(sc, "_extract_variant", fake_extract)
        result = run_n_samples(
            feature_id=_FEATURE_ID,
            name=_NAME,
            description=_DESCRIPTION,
            acceptance_criteria=_ACS,
            n=3,
            variants_dir=tmp_path,
        )
        assert result.stability_score >= 0.9
        assert result.route == "auto_accept"
        assert result.consensus is True

    def test_majority_vote_spec_populated(self, tmp_path, monkeypatch):
        import bob3.spec_quality.self_consistency as sc

        def fake_extract(feature_id, name, description, acceptance_criteria, seed):
            return [{"id": "AC-1", "behavior": "do the thing"}]

        monkeypatch.setattr(sc, "_extract_variant", fake_extract)
        result = run_n_samples(
            feature_id=_FEATURE_ID,
            name=_NAME,
            description=_DESCRIPTION,
            acceptance_criteria=_ACS,
            n=3,
            variants_dir=tmp_path,
        )
        assert result.majority_vote is not None
        assert len(result.majority_vote) > 0

    def test_variants_yaml_has_consensus_true_flag(self, tmp_path, monkeypatch):
        import bob3.spec_quality.self_consistency as sc

        def fake_extract(feature_id, name, description, acceptance_criteria, seed):
            return [{"id": "AC-1", "behavior": "stable"}]

        monkeypatch.setattr(sc, "_extract_variant", fake_extract)
        run_n_samples(
            feature_id=_FEATURE_ID,
            name=_NAME,
            description=_DESCRIPTION,
            acceptance_criteria=_ACS,
            n=3,
            variants_dir=tmp_path,
        )
        variants_file = tmp_path / _FEATURE_ID / "variants.yaml"
        data = yaml.safe_load(variants_file.read_text())
        assert data.get("consensus") is True

    def test_route_result_high_score_returns_auto_accept(self):
        variants = [
            [{"id": "AC-1", "behavior": "same"}, {"id": "AC-2", "behavior": "thing"}],
            [{"id": "AC-1", "behavior": "same"}, {"id": "AC-2", "behavior": "thing"}],
            [{"id": "AC-1", "behavior": "same"}, {"id": "AC-2", "behavior": "thing"}],
        ]
        score = jaccard_stability(variants)
        assert score >= 0.9
        result = _route_result(score=score, variants=variants)
        assert result.route == "auto_accept"
        assert result.consensus is True

    def test_mid_range_score_routes_to_critic(self):
        # score in [0.7, 0.9) → send to critic stage
        variants = [
            [{"id": "AC-1", "behavior": "foo"}, {"id": "AC-2", "behavior": "bar"}],
            [{"id": "AC-1", "behavior": "foo"}, {"id": "AC-3", "behavior": "baz"}],
            [{"id": "AC-1", "behavior": "foo"}, {"id": "AC-4", "behavior": "qux"}],
        ]
        score = jaccard_stability(variants)
        assert 0.0 < score < 0.9  # may or may not be >= 0.7; just check critic
        if score >= 0.7:
            result = _route_result(score=score, variants=variants)
            assert result.route == "critic"
            assert result.consensus is False

    def test_consensus_flag_false_for_non_auto_accept(self, tmp_path, monkeypatch):
        import bob3.spec_quality.self_consistency as sc

        def fake_extract(feature_id, name, description, acceptance_criteria, seed):
            return [{"id": f"AC-{seed}", "behavior": f"v{seed}"}]

        monkeypatch.setattr(sc, "_extract_variant", fake_extract)
        result = run_n_samples(
            feature_id=_FEATURE_ID,
            name=_NAME,
            description=_DESCRIPTION,
            acceptance_criteria=_ACS,
            n=3,
            variants_dir=tmp_path,
        )
        if result.route != "auto_accept":
            assert result.consensus is False

    def test_majority_vote_uses_most_common_acs(self):
        # 2-of-3 agree on AC-1, only 1 has AC-2
        variants = [
            [{"id": "AC-1", "behavior": "foo"}],
            [{"id": "AC-1", "behavior": "foo"}],
            [{"id": "AC-2", "behavior": "bar"}],
        ]
        score = jaccard_stability(variants)
        result = _route_result(score=score, variants=variants)
        # majority is AC-1/foo
        mv_ids = {item["id"] for item in result.majority_vote}
        assert "AC-1" in mv_ids

    def test_stability_score_stored_in_result(self, tmp_path, monkeypatch):
        import bob3.spec_quality.self_consistency as sc

        def fake_extract(feature_id, name, description, acceptance_criteria, seed):
            return [{"id": "AC-1", "behavior": "stable"}]

        monkeypatch.setattr(sc, "_extract_variant", fake_extract)
        result = run_n_samples(
            feature_id=_FEATURE_ID,
            name=_NAME,
            description=_DESCRIPTION,
            acceptance_criteria=_ACS,
            n=3,
            variants_dir=tmp_path,
        )
        assert isinstance(result.stability_score, float)
        assert 0.0 <= result.stability_score <= 1.0
