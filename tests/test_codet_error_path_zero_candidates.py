"""Tests for error path: spawn_k_tests(K=0) raises ValueError with 'K must be >= 1'."""

from __future__ import annotations

import pytest

from bob3.orchestrator.codet_triangulation import (
    spawn_k_tests,
    spawn_k_impls,
)


class TestSpawnKTestsZeroCandidates:
    def test_k_zero_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError) as exc_info:
            spawn_k_tests(
                feature_id="feat-zero-k",
                acceptance_criteria=["AC: does something"],
                K=0,
                workspace=tmp_path,
            )
        assert "K must be >= 1" in str(exc_info.value)

    def test_k_zero_error_message_exact_substring(self, tmp_path):
        try:
            spawn_k_tests(
                feature_id="feat-zero-exact",
                acceptance_criteria=[],
                K=0,
                workspace=tmp_path,
            )
        except ValueError as e:
            assert "K must be >= 1" in str(e)
        else:
            pytest.fail("Expected ValueError was not raised")

    def test_k_negative_also_raises(self, tmp_path):
        with pytest.raises(ValueError) as exc_info:
            spawn_k_tests(
                feature_id="feat-neg-k",
                acceptance_criteria=["AC: something"],
                K=-5,
                workspace=tmp_path,
            )
        assert "K must be >= 1" in str(exc_info.value)

    def test_k_one_does_not_raise(self, tmp_path):
        result = spawn_k_tests(
            feature_id="feat-k-one",
            acceptance_criteria=["AC: something"],
            K=1,
            workspace=tmp_path,
        )
        assert len(result) == 1

    def test_k_three_returns_three_candidates(self, tmp_path):
        result = spawn_k_tests(
            feature_id="feat-k-three",
            acceptance_criteria=["AC: a", "AC: b"],
            K=3,
            workspace=tmp_path,
        )
        assert len(result) == 3


class TestSpawnKImplsZeroCandidates:
    def test_k_zero_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError) as exc_info:
            spawn_k_impls(
                feature_id="feat-impl-zero-k",
                acceptance_criteria=["AC: something"],
                K=0,
                workspace=tmp_path,
            )
        assert "K must be >= 1" in str(exc_info.value)

    def test_k_two_returns_two_impls(self, tmp_path):
        result = spawn_k_impls(
            feature_id="feat-impl-k-two",
            acceptance_criteria=["AC: something"],
            K=2,
            workspace=tmp_path,
        )
        assert len(result) == 2
