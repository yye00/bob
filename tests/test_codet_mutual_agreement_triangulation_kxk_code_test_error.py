"""Error-path tests for CodeT KxK mutual-agreement triangulation.

AC: invalid input raises ValueError and the function does not silently succeed
(error path).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.codet_triangulation import generate_kxk_matrix, mutual_agreement_scorer
from bob3.orchestrator.codet_triangulation import (
    CandidateImpl,
    CandidateTestSet,
    spawn_k_impls,
    spawn_k_tests,
)


class TestGenerateKxKMatrixErrors:
    def test_empty_impls_raises_value_error(self, tmp_path):
        """Empty impls list must raise ValueError, not silently return."""
        test_sets = spawn_k_tests("error-empty-impls", ["AC1"], K=1, workspace=tmp_path)
        with pytest.raises(ValueError):
            generate_kxk_matrix([], test_sets, workspace=tmp_path)

    def test_empty_test_sets_raises_value_error(self, tmp_path):
        """Empty test_sets list must raise ValueError, not silently return."""
        impls = spawn_k_impls("error-empty-tests", ["AC1"], K=1, workspace=tmp_path)
        with pytest.raises(ValueError):
            generate_kxk_matrix(impls, [], workspace=tmp_path)

    def test_both_empty_raises_value_error(self, tmp_path):
        """Both lists empty: must raise ValueError."""
        with pytest.raises(ValueError):
            generate_kxk_matrix([], [], workspace=tmp_path)

    def test_error_message_mentions_impls_when_impls_empty(self, tmp_path):
        """ValueError message should reference 'impls' when impls is the problem."""
        test_sets = spawn_k_tests("error-msg-impls", ["AC1"], K=1, workspace=tmp_path)
        with pytest.raises(ValueError, match="impls"):
            generate_kxk_matrix([], test_sets, workspace=tmp_path)

    def test_error_message_mentions_test_sets_when_tests_empty(self, tmp_path):
        """ValueError message should reference 'test_sets' when test_sets is the problem."""
        impls = spawn_k_impls("error-msg-tests", ["AC1"], K=1, workspace=tmp_path)
        with pytest.raises(ValueError, match="test_sets"):
            generate_kxk_matrix(impls, [], workspace=tmp_path)


class TestMutualAgreementScorerErrors:
    def test_empty_all_impls_raises_value_error(self, tmp_path):
        """all_impls must not be empty — raises ValueError, not silent."""
        test_sets = spawn_k_tests("error-mas-impls", ["AC1"], K=1, workspace=tmp_path)
        dummy_impl = CandidateImpl(
            index=0, impl_path=tmp_path / "impl.py", content=""
        )
        with pytest.raises(ValueError):
            mutual_agreement_scorer(
                dummy_impl, test_sets[0], [], test_sets, workspace=tmp_path
            )

    def test_error_message_mentions_all_impls(self, tmp_path):
        """ValueError for empty all_impls should reference 'all_impls'."""
        test_sets = spawn_k_tests("error-mas-msg", ["AC1"], K=1, workspace=tmp_path)
        dummy_impl = CandidateImpl(
            index=0, impl_path=tmp_path / "impl.py", content=""
        )
        with pytest.raises(ValueError, match="all_impls"):
            mutual_agreement_scorer(
                dummy_impl, test_sets[0], [], test_sets, workspace=tmp_path
            )

    def test_does_not_silently_succeed_on_empty_input(self, tmp_path):
        """Confirm no result is returned when input is invalid."""
        test_sets = spawn_k_tests("error-silent", ["AC1"], K=1, workspace=tmp_path)
        dummy_impl = CandidateImpl(
            index=0, impl_path=tmp_path / "impl.py", content=""
        )
        result = None
        raised = False
        try:
            result = mutual_agreement_scorer(
                dummy_impl, test_sets[0], [], test_sets, workspace=tmp_path
            )
        except ValueError:
            raised = True

        assert raised, "Expected ValueError but function returned silently"
        assert result is None
