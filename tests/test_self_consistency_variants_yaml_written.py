"""Tests that persist_variants writes specs/<feature>/variants.yaml correctly.

Feature: b54b799e-f4cc-4136-b35a-e1c8a4ef32be
Spec: Spec self-consistency — N-sample stability check pre-critic
"""

from __future__ import annotations

import yaml
import pytest

from bob3.spec_quality.self_consistency import (
    run_n_samples,
    persist_variants,
    SelfConsistencyResult,
    jaccard_stability,
    _route_result,
)

_FEATURE_ID = "test-feature-variants-yaml"
_NAME = "Variants YAML feature"
_DESCRIPTION = "A feature to test variants.yaml persistence"
_ACS = ["File exists: src/foo.py", "Function defined: foo.bar"]


class TestVariantsYamlWritten:
    def test_variants_yaml_created_by_run_n_samples(self, tmp_path):
        result = run_n_samples(
            feature_id=_FEATURE_ID,
            name=_NAME,
            description=_DESCRIPTION,
            acceptance_criteria=_ACS,
            n=3,
            variants_dir=tmp_path,
        )
        variants_file = tmp_path / _FEATURE_ID / "variants.yaml"
        assert variants_file.exists(), "variants.yaml was not created"

    def test_variants_yaml_contains_feature_id(self, tmp_path):
        run_n_samples(
            feature_id=_FEATURE_ID,
            name=_NAME,
            description=_DESCRIPTION,
            acceptance_criteria=_ACS,
            n=3,
            variants_dir=tmp_path,
        )
        data = yaml.safe_load((tmp_path / _FEATURE_ID / "variants.yaml").read_text())
        assert data["feature_id"] == _FEATURE_ID

    def test_variants_yaml_contains_stability_score(self, tmp_path):
        run_n_samples(
            feature_id=_FEATURE_ID,
            name=_NAME,
            description=_DESCRIPTION,
            acceptance_criteria=_ACS,
            n=3,
            variants_dir=tmp_path,
        )
        data = yaml.safe_load((tmp_path / _FEATURE_ID / "variants.yaml").read_text())
        assert "stability_score" in data
        assert isinstance(data["stability_score"], float)
        assert 0.0 <= data["stability_score"] <= 1.0

    def test_variants_yaml_contains_route(self, tmp_path):
        run_n_samples(
            feature_id=_FEATURE_ID,
            name=_NAME,
            description=_DESCRIPTION,
            acceptance_criteria=_ACS,
            n=3,
            variants_dir=tmp_path,
        )
        data = yaml.safe_load((tmp_path / _FEATURE_ID / "variants.yaml").read_text())
        assert "route" in data
        assert data["route"] in ("clarification", "critic", "auto_accept")

    def test_variants_yaml_contains_variants_list(self, tmp_path):
        run_n_samples(
            feature_id=_FEATURE_ID,
            name=_NAME,
            description=_DESCRIPTION,
            acceptance_criteria=_ACS,
            n=3,
            variants_dir=tmp_path,
        )
        data = yaml.safe_load((tmp_path / _FEATURE_ID / "variants.yaml").read_text())
        assert "variants" in data
        assert isinstance(data["variants"], list)
        assert len(data["variants"]) == 3

    def test_persist_variants_public_function_returns_path(self, tmp_path):
        variants = [
            [{"id": "AC-1", "behavior": "foo"}],
            [{"id": "AC-1", "behavior": "foo"}],
        ]
        score = jaccard_stability(variants)
        result = _route_result(score=score, variants=variants)
        path = persist_variants(_FEATURE_ID, variants, result, tmp_path)
        assert path.exists()
        assert path.name == "variants.yaml"

    def test_variants_yaml_has_consensus_field(self, tmp_path, monkeypatch):
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
        data = yaml.safe_load((tmp_path / _FEATURE_ID / "variants.yaml").read_text())
        assert "consensus" in data

    def test_variants_yaml_disagreeing_slots_when_low_score(self, tmp_path, monkeypatch):
        import bob3.spec_quality.self_consistency as sc

        def fake_extract(feature_id, name, description, acceptance_criteria, seed):
            return [{"id": f"AC-{seed}", "behavior": f"unique-behavior-{seed}"}]

        monkeypatch.setattr(sc, "_extract_variant", fake_extract)
        run_n_samples(
            feature_id=_FEATURE_ID,
            name=_NAME,
            description=_DESCRIPTION,
            acceptance_criteria=_ACS,
            n=3,
            variants_dir=tmp_path,
        )
        data = yaml.safe_load((tmp_path / _FEATURE_ID / "variants.yaml").read_text())
        assert "disagreeing_slots" in data
        assert len(data["disagreeing_slots"]) > 0
