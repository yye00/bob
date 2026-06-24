"""Tests for codet_mutual_agreement_triangulation_kxk_code_test_matrix module."""

from __future__ import annotations

import pytest

from bob3.codet_mutual_agreement_triangulation_kxk_code_test_matrix import (
    codet_mutual_agreement_triangulation_kxk_code_test_matrix,
)


def test_codet_mutual_agreement_triangulation_kxk_code_test_matrix():
    """Primary AC test: function exists, is callable, and returns a valid result."""
    result = codet_mutual_agreement_triangulation_kxk_code_test_matrix(
        feature_id="test-feature-001",
        acceptance_criteria=["File exists: src/foo.py", "Function defined: foo.bar"],
        K=2,
    )
    # Must return a dict with required keys
    assert isinstance(result, dict)
    assert "winner_impl_index" in result
    assert "winner_test_index" in result
    assert "winner_score" in result
    assert "k" in result
    assert result["k"] == 2
    assert isinstance(result["winner_impl_index"], int)
    assert isinstance(result["winner_test_index"], int)
    assert isinstance(result["winner_score"], float)
    assert result["winner_impl_index"] >= 0
    assert result["winner_test_index"] >= 0
    assert result["winner_score"] >= 0.0


def test_returns_dict_with_cells():
    result = codet_mutual_agreement_triangulation_kxk_code_test_matrix(
        feature_id="test-feature-002",
        acceptance_criteria=["AC1"],
        K=2,
    )
    assert "cells" in result
    assert isinstance(result["cells"], list)
    assert len(result["cells"]) == 4  # K*K = 2*2


def test_k_equals_one_produces_single_cell():
    result = codet_mutual_agreement_triangulation_kxk_code_test_matrix(
        feature_id="test-feature-k1",
        acceptance_criteria=["AC1"],
        K=1,
    )
    assert result["k"] == 1
    assert len(result["cells"]) == 1


def test_k_zero_raises_value_error():
    with pytest.raises(ValueError, match="K must be >= 1"):
        codet_mutual_agreement_triangulation_kxk_code_test_matrix(
            feature_id="test-feature-k0",
            acceptance_criteria=["AC1"],
            K=0,
        )


def test_k_negative_raises_value_error():
    with pytest.raises(ValueError, match="K must be >= 1"):
        codet_mutual_agreement_triangulation_kxk_code_test_matrix(
            feature_id="test-feature-neg",
            acceptance_criteria=["AC1"],
            K=-1,
        )


def test_empty_acceptance_criteria_allowed():
    result = codet_mutual_agreement_triangulation_kxk_code_test_matrix(
        feature_id="test-feature-empty-ac",
        acceptance_criteria=[],
        K=1,
    )
    assert isinstance(result, dict)
    assert result["k"] == 1


def test_cells_have_required_fields():
    result = codet_mutual_agreement_triangulation_kxk_code_test_matrix(
        feature_id="test-feature-fields",
        acceptance_criteria=["AC1"],
        K=2,
    )
    for cell in result["cells"]:
        assert "impl_index" in cell
        assert "test_index" in cell
        assert "score" in cell
        assert isinstance(cell["impl_index"], int)
        assert isinstance(cell["test_index"], int)
        assert isinstance(cell["score"], float)


def test_winner_is_max_scoring_cell():
    result = codet_mutual_agreement_triangulation_kxk_code_test_matrix(
        feature_id="test-feature-winner",
        acceptance_criteria=["AC1"],
        K=2,
    )
    max_score = max(c["score"] for c in result["cells"])
    assert result["winner_score"] == pytest.approx(max_score)


def test_winner_indices_correspond_to_real_cell():
    result = codet_mutual_agreement_triangulation_kxk_code_test_matrix(
        feature_id="test-feature-winner-idx",
        acceptance_criteria=["AC1"],
        K=2,
    )
    winner_pair = (result["winner_impl_index"], result["winner_test_index"])
    cell_pairs = {(c["impl_index"], c["test_index"]) for c in result["cells"]}
    assert winner_pair in cell_pairs


def test_feature_id_included_in_result():
    result = codet_mutual_agreement_triangulation_kxk_code_test_matrix(
        feature_id="feature-xyz-123",
        acceptance_criteria=["AC1"],
        K=1,
    )
    assert result.get("feature_id") == "feature-xyz-123"
