"""Error path tests for retry_strategy — invalid input raises ValueError and does not silently succeed.

AC: pytest: tests/test_research_augmented_retry_error.py — invalid input raises ValueError
and the function does not silently succeed (error path).
"""

import pytest

from bob.retry_strategy import (
    classify_failure,
    research_augmented_retry,
    spawn_research_agent,
)


class TestClassifyFailureErrorPath:
    def test_non_dict_raises_value_error(self):
        with pytest.raises(ValueError):
            classify_failure("not a dict")

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            classify_failure(None)

    def test_list_raises_value_error(self):
        with pytest.raises(ValueError):
            classify_failure(["ImportError"])

    def test_int_raises_value_error(self):
        with pytest.raises(ValueError):
            classify_failure(42)

    def test_explicit_invalid_failure_class_raises_value_error(self):
        with pytest.raises(ValueError):
            classify_failure({"failure_class": "totally_invalid_class"})

    def test_explicit_none_failure_class_raises_value_error(self):
        with pytest.raises(ValueError):
            classify_failure({"failure_class": None})

    def test_error_message_is_descriptive(self):
        with pytest.raises(ValueError, match="failure_class"):
            classify_failure({"failure_class": "bad_value"})


class TestSpawnResearchAgentErrorPath:
    def test_invalid_failure_class_raises_value_error(self):
        with pytest.raises(ValueError):
            spawn_research_agent("not_a_real_class")

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            spawn_research_agent("")

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            spawn_research_agent(None)

    def test_error_message_is_descriptive(self):
        with pytest.raises(ValueError, match="not a valid failure class"):
            spawn_research_agent("bogus_class")

    def test_does_not_silently_succeed_on_invalid_input(self):
        raised = False
        try:
            result = spawn_research_agent("invalid_class_name")
        except ValueError:
            raised = True
        assert raised, "spawn_research_agent must raise ValueError for invalid input, not silently return"


class TestResearchAugmentedRetryErrorPath:
    def test_non_dict_failure_info_raises_value_error(self):
        with pytest.raises(ValueError):
            research_augmented_retry(
                refinement_attempts=2,
                failure_info="not a dict",
                base_prompt="Prompt.",
                feature_id="test-error-str",
                attempt_number=2,
            )

    def test_none_failure_info_raises_value_error(self):
        with pytest.raises(ValueError):
            research_augmented_retry(
                refinement_attempts=2,
                failure_info=None,
                base_prompt="Prompt.",
                feature_id="test-error-none",
                attempt_number=2,
            )

    def test_list_failure_info_raises_value_error(self):
        with pytest.raises(ValueError):
            research_augmented_retry(
                refinement_attempts=2,
                failure_info=["ImportError"],
                base_prompt="Prompt.",
                feature_id="test-error-list",
                attempt_number=2,
            )

    def test_explicit_invalid_failure_class_in_failure_info_raises_value_error(self):
        with pytest.raises(ValueError):
            research_augmented_retry(
                refinement_attempts=2,
                failure_info={"failure_class": "totally_invalid"},
                base_prompt="Prompt.",
                feature_id="test-error-invalid-class",
                attempt_number=2,
            )

    def test_does_not_silently_succeed_on_none_failure_info(self):
        raised = False
        try:
            research_augmented_retry(
                refinement_attempts=2,
                failure_info=None,
                base_prompt="Prompt.",
                feature_id="test-silent-fail",
                attempt_number=2,
            )
        except ValueError:
            raised = True
        assert raised, "research_augmented_retry must raise ValueError for None failure_info"
