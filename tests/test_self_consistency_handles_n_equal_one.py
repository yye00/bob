"""Tests that handle_n_equal_one returns score=1.0 trivially when N=1.

Feature: b54b799e-f4cc-4136-b35a-e1c8a4ef32be
Spec: Spec self-consistency — N-sample stability check pre-critic
"""

from __future__ import annotations

import pytest

from bob.spec_quality.self_consistency import (
    handle_n_equal_one,
    run_n_samples,
    jaccard_stability,
)

_FEATURE_ID = "test-feature-n-one"
_NAME = "N=1 feature"
_DESCRIPTION = "A feature where N=1 sample is requested"
_ACS = ["File exists: src/foo.py", "Function defined: foo.bar"]


class TestHandlesNEqualOne:
    def test_handle_n_equal_one_returns_1_0(self):
        score = handle_n_equal_one(
            feature_id=_FEATURE_ID,
            name=_NAME,
            description=_DESCRIPTION,
            acceptance_criteria=_ACS,
        )
        assert score == pytest.approx(1.0)

    def test_handle_n_equal_one_returns_float(self):
        score = handle_n_equal_one(
            feature_id=_FEATURE_ID,
            name=_NAME,
            description=_DESCRIPTION,
            acceptance_criteria=_ACS,
        )
        assert isinstance(score, float)

    def test_run_n_samples_n_1_yields_score_1(self, tmp_path):
        result = run_n_samples(
            feature_id=_FEATURE_ID,
            name=_NAME,
            description=_DESCRIPTION,
            acceptance_criteria=_ACS,
            n=1,
            variants_dir=tmp_path,
        )
        assert result.stability_score == pytest.approx(1.0)

    def test_run_n_samples_n_1_routes_to_auto_accept(self, tmp_path):
        result = run_n_samples(
            feature_id=_FEATURE_ID,
            name=_NAME,
            description=_DESCRIPTION,
            acceptance_criteria=_ACS,
            n=1,
            variants_dir=tmp_path,
        )
        assert result.route == "auto_accept"

    def test_jaccard_single_variant_returns_1(self):
        variants = [[{"id": "AC-1", "behavior": "do stuff"}]]
        score = jaccard_stability(variants)
        assert score == pytest.approx(1.0)

    def test_jaccard_empty_returns_1(self):
        score = jaccard_stability([])
        assert score == pytest.approx(1.0)

    def test_handle_n_equal_one_idempotent(self):
        score1 = handle_n_equal_one(_FEATURE_ID, _NAME, _DESCRIPTION, _ACS)
        score2 = handle_n_equal_one(_FEATURE_ID, _NAME, _DESCRIPTION, _ACS)
        assert score1 == score2 == pytest.approx(1.0)
