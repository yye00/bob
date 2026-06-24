"""Boundary tests for retry_strategy — empty, zero, or minimum input returns a well-defined result.

AC: pytest: tests/test_research_augmented_retry_boundary.py — empty, zero, or minimum
input returns a well-defined result rather than raising (boundary case).
"""

import pytest

from bob.retry_strategy import (
    classify_failure,
    research_augmented_retry,
    spawn_research_agent,
)


class TestClassifyFailureBoundary:
    def test_empty_dict_returns_unknown(self):
        result = classify_failure({})
        assert result == "unknown"

    def test_dict_with_empty_strings_returns_unknown(self):
        result = classify_failure({"error_type": "", "message": ""})
        assert result == "unknown"

    def test_dict_with_none_values_returns_unknown(self):
        result = classify_failure({"error_type": None, "message": None})
        assert result == "unknown"

    def test_dict_with_only_traceback_key_unknown(self):
        result = classify_failure({"traceback": ""})
        assert result == "unknown"

    def test_minimum_import_error_signal(self):
        result = classify_failure({"error_type": "ImportError"})
        assert result == "import_error"

    def test_minimum_message_only_signal(self):
        result = classify_failure({"message": "ambiguous"})
        assert result == "ambiguous_ac"


class TestSpawnResearchAgentBoundary:
    def test_unknown_returns_false_not_raises(self):
        result = spawn_research_agent("unknown")
        assert result is False

    def test_each_valid_non_unknown_class_returns_true(self):
        valid_classes = [
            "missing_test_file",
            "import_error",
            "type_mismatch",
            "contract_violation",
            "empty_impl",
            "ambiguous_ac",
        ]
        for fc in valid_classes:
            result = spawn_research_agent(fc)
            assert result is True, f"Expected True for {fc!r}, got {result!r}"


class TestResearchAugmentedRetryBoundary:
    def test_zero_refinement_attempts_does_not_raise(self):
        result = research_augmented_retry(
            refinement_attempts=0,
            failure_info={"error_type": "ImportError", "message": "cannot import foo"},
            base_prompt="Prompt.",
            feature_id="test-zero-attempts",
            attempt_number=1,
        )
        assert result["triggered"] is False
        assert isinstance(result, dict)

    def test_empty_failure_info_does_not_raise(self):
        result = research_augmented_retry(
            refinement_attempts=0,
            failure_info={},
            base_prompt="Prompt.",
            feature_id="test-empty-failure",
            attempt_number=1,
        )
        assert isinstance(result, dict)
        assert result["failure_class"] == "unknown"

    def test_empty_base_prompt_does_not_raise(self):
        result = research_augmented_retry(
            refinement_attempts=0,
            failure_info={},
            base_prompt="",
            feature_id="test-empty-prompt",
            attempt_number=1,
        )
        assert isinstance(result, dict)
        assert result["prompt"] == ""

    def test_minimum_threshold_exactly_2(self):
        result = research_augmented_retry(
            refinement_attempts=2,
            failure_info={"error_type": "ImportError", "message": "cannot import foo"},
            base_prompt="Min threshold.",
            feature_id="test-min-threshold",
            attempt_number=2,
        )
        assert result["triggered"] is True

    def test_one_below_threshold_exactly_1(self):
        result = research_augmented_retry(
            refinement_attempts=1,
            failure_info={"error_type": "ImportError", "message": "cannot import foo"},
            base_prompt="Below threshold.",
            feature_id="test-below-threshold",
            attempt_number=1,
        )
        assert result["triggered"] is False

    def test_attempt_number_1_is_valid_minimum(self):
        result = research_augmented_retry(
            refinement_attempts=2,
            failure_info={"error_type": "ImportError", "message": "cannot import foo"},
            base_prompt="Prompt.",
            feature_id="test-attempt-1",
            attempt_number=1,
        )
        assert isinstance(result, dict)
        assert result["triggered"] is True

    def test_workspace_none_does_not_raise_when_not_triggered(self):
        result = research_augmented_retry(
            refinement_attempts=0,
            failure_info={},
            base_prompt="Prompt.",
            feature_id="test-no-workspace",
            attempt_number=1,
            workspace=None,
        )
        assert result["triggered"] is False

    def test_strategies_empty_when_not_triggered(self):
        result = research_augmented_retry(
            refinement_attempts=0,
            failure_info={},
            base_prompt="Prompt.",
            feature_id="test-empty-strategies",
            attempt_number=1,
        )
        assert result["strategies"] == []

    def test_strategies_path_none_when_not_triggered(self):
        result = research_augmented_retry(
            refinement_attempts=0,
            failure_info={},
            base_prompt="Prompt.",
            feature_id="test-paths-none",
            attempt_number=1,
        )
        assert result["strategies_path"] is None
        assert result["prompt_path"] is None
