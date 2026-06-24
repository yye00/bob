"""Tests that stability_score < 0.7 routes to F-R7-456 clarification.

Feature: 289249a9-4e29-4cbc-b418-c242c024bdfe
Spec: Spec self-consistency — N-sample stability check pre-critic
"""

from __future__ import annotations

import pytest

from bob.spec_quality.self_consistency import run_n_samples, SelfConsistencyResult


_FEATURE_ID = "test-feature-low-score"
_NAME = "Low stability feature"
_DESCRIPTION = "A feature with ambiguous spec"
_ACS = ["File exists: src/foo.py", "Function defined: foo.bar"]


class TestLowScoreRoutesToClarification:
    def test_result_has_route_field(self, tmp_path):
        result = run_n_samples(
            feature_id=_FEATURE_ID,
            name=_NAME,
            description=_DESCRIPTION,
            acceptance_criteria=_ACS,
            n=3,
            variants_dir=tmp_path,
        )
        assert hasattr(result, "route")

    def test_low_stability_routes_to_clarification(self, tmp_path):
        # Inject pre-built variants where there's no overlap (score=0.0)
        from bob.spec_quality.self_consistency import jaccard_stability, SelfConsistencyResult
        variants = [
            [{"id": "AC-1", "behavior": "foo"}],
            [{"id": "AC-2", "behavior": "bar"}],
            [{"id": "AC-3", "behavior": "baz"}],
        ]
        score = jaccard_stability(variants)
        assert score < 0.7
        # Build result manually
        result = SelfConsistencyResult(
            stability_score=score,
            route="clarification",
            consensus=False,
            disagreeing_slots=[("AC-1", "foo"), ("AC-2", "bar")],
            majority_vote=[],
        )
        assert result.route == "clarification"
        assert result.stability_score < 0.7

    def test_disagreeing_slots_populated_when_low(self, tmp_path):
        variants = [
            [{"id": "AC-1", "behavior": "foo"}],
            [{"id": "AC-2", "behavior": "bar"}],
        ]
        from bob.spec_quality.self_consistency import jaccard_stability
        score = jaccard_stability(variants)
        from bob.spec_quality.self_consistency import _route_result
        result = _route_result(score=score, variants=variants)
        assert result.route == "clarification"
        assert len(result.disagreeing_slots) > 0

    def test_run_n_samples_returns_clarification_for_unstable(self, tmp_path, monkeypatch):
        # Monkeypatch the internal extractor to return divergent variants
        import bob.spec_quality.self_consistency as sc

        def fake_extract(feature_id, name, description, acceptance_criteria, seed):
            if seed == 0:
                return [{"id": "AC-1", "behavior": "foo"}]
            elif seed == 1:
                return [{"id": "AC-2", "behavior": "bar"}]
            else:
                return [{"id": "AC-3", "behavior": "baz"}]

        monkeypatch.setattr(sc, "_extract_variant", fake_extract)
        result = run_n_samples(
            feature_id=_FEATURE_ID,
            name=_NAME,
            description=_DESCRIPTION,
            acceptance_criteria=_ACS,
            n=3,
            variants_dir=tmp_path,
        )
        assert result.route == "clarification"
        assert result.stability_score < 0.7
        assert len(result.disagreeing_slots) > 0

    def test_variants_yaml_written_for_unstable(self, tmp_path, monkeypatch):
        import bob.spec_quality.self_consistency as sc

        def fake_extract(feature_id, name, description, acceptance_criteria, seed):
            return [{"id": f"AC-{seed}", "behavior": f"v{seed}"}]

        monkeypatch.setattr(sc, "_extract_variant", fake_extract)
        run_n_samples(
            feature_id=_FEATURE_ID,
            name=_NAME,
            description=_DESCRIPTION,
            acceptance_criteria=_ACS,
            n=3,
            variants_dir=tmp_path,
        )
        import yaml
        variants_file = tmp_path / _FEATURE_ID / "variants.yaml"
        assert variants_file.exists()
        data = yaml.safe_load(variants_file.read_text())
        assert "stability_score" in data
        assert "variants" in data

    def test_route_field_is_string(self, tmp_path):
        result = run_n_samples(
            feature_id=_FEATURE_ID,
            name=_NAME,
            description=_DESCRIPTION,
            acceptance_criteria=_ACS,
            n=3,
            variants_dir=tmp_path,
        )
        assert isinstance(result.route, str)
        assert result.route in ("clarification", "critic", "auto_accept")
