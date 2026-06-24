"""Tests for retry_strategy module — research_augmented_retry, classify_failure, spawn_research_agent."""

import pathlib
import pytest

from bob.retry_strategy import (
    classify_failure,
    research_augmented_retry,
    spawn_research_agent,
)


class TestClassifyFailure:
    def test_classifies_import_error(self):
        result = classify_failure({"error_type": "ImportError", "message": "cannot import name foo"})
        assert result == "import_error"

    def test_classifies_file_not_found(self):
        result = classify_failure({"error_type": "FileNotFoundError", "message": "no such file"})
        assert result == "missing_test_file"

    def test_classifies_type_error(self):
        result = classify_failure({"error_type": "TypeError", "message": "type mismatch"})
        assert result == "type_mismatch"

    def test_classifies_ambiguous_ac(self):
        result = classify_failure({"message": "ambiguous acceptance criteria, unclear"})
        assert result == "ambiguous_ac"

    def test_classifies_empty_impl(self):
        result = classify_failure({"error_type": "NotImplementedError", "message": "stub"})
        assert result == "empty_impl"

    def test_classifies_unknown(self):
        result = classify_failure({"error_type": "SomeWeirdError", "message": "completely unrecognized"})
        assert result == "unknown"

    def test_explicit_failure_class_key_takes_precedence(self):
        result = classify_failure({"failure_class": "empty_impl", "error_type": "ImportError"})
        assert result == "empty_impl"

    def test_returns_string(self):
        result = classify_failure({"error_type": "ImportError", "message": "msg"})
        assert isinstance(result, str)


class TestSpawnResearchAgent:
    def test_returns_true_for_import_error(self):
        assert spawn_research_agent("import_error") is True

    def test_returns_true_for_missing_test_file(self):
        assert spawn_research_agent("missing_test_file") is True

    def test_returns_true_for_type_mismatch(self):
        assert spawn_research_agent("type_mismatch") is True

    def test_returns_true_for_ambiguous_ac(self):
        assert spawn_research_agent("ambiguous_ac") is True

    def test_returns_false_for_unknown(self):
        assert spawn_research_agent("unknown") is False

    def test_returns_bool(self):
        result = spawn_research_agent("import_error")
        assert isinstance(result, bool)


class TestResearchAugmentedRetry:
    def test_returns_dict_with_required_keys(self):
        result = research_augmented_retry(
            refinement_attempts=0,
            failure_info={"error_type": "ImportError", "message": "cannot import foo"},
            base_prompt="Implement the feature.",
            feature_id="test-feature-123",
            attempt_number=1,
        )
        assert isinstance(result, dict)
        for key in ("triggered", "failure_class", "strategies", "prompt", "strategies_path", "prompt_path"):
            assert key in result

    def test_does_not_trigger_below_threshold(self):
        result = research_augmented_retry(
            refinement_attempts=1,
            failure_info={"error_type": "ImportError", "message": "cannot import foo"},
            base_prompt="Implement the feature.",
            feature_id="test-feature-abc",
            attempt_number=1,
        )
        assert result["triggered"] is False
        assert result["strategies"] == []
        assert result["prompt"] == "Implement the feature."
        assert result["strategies_path"] is None
        assert result["prompt_path"] is None

    def test_triggers_at_threshold_with_classifiable_failure(self):
        result = research_augmented_retry(
            refinement_attempts=2,
            failure_info={"error_type": "ImportError", "message": "cannot import foo"},
            base_prompt="Implement the feature.",
            feature_id="test-feature-trigger",
            attempt_number=2,
        )
        assert result["triggered"] is True
        assert result["failure_class"] == "import_error"
        assert len(result["strategies"]) > 0
        assert result["prompt"] != "Implement the feature."
        assert "Research-Augmented Retry" in result["prompt"]

    def test_does_not_trigger_on_unknown_failure_class(self):
        result = research_augmented_retry(
            refinement_attempts=3,
            failure_info={"error_type": "SomeWeirdError", "message": "completely unrecognized"},
            base_prompt="Implement the feature.",
            feature_id="test-feature-unknown",
            attempt_number=3,
        )
        assert result["triggered"] is False
        assert result["failure_class"] == "unknown"
        assert result["strategies"] == []

    def test_persists_strategies_and_prompt_when_triggered(self, tmp_path):
        result = research_augmented_retry(
            refinement_attempts=2,
            failure_info={"error_type": "ImportError", "message": "cannot import foo"},
            base_prompt="Base prompt text.",
            feature_id="test-persist-feature",
            attempt_number=2,
            workspace=tmp_path,
        )
        assert result["triggered"] is True
        strategies_path = pathlib.Path(result["strategies_path"])
        assert strategies_path.exists()
        assert strategies_path.suffix == ".yaml"

        prompt_path = pathlib.Path(result["prompt_path"])
        assert prompt_path.exists()
        content = prompt_path.read_text()
        assert "Base prompt text." in content
        assert "Research-Augmented Retry" in content

    def test_prompt_contains_strategy_titles_when_triggered(self):
        result = research_augmented_retry(
            refinement_attempts=3,
            failure_info={"error_type": "TypeError", "message": "type mismatch"},
            base_prompt="Original implementation prompt.",
            feature_id="test-prompt-injection",
            attempt_number=3,
        )
        assert result["triggered"] is True
        for strategy in result["strategies"]:
            assert strategy["title"] in result["prompt"]

    def test_strategy_dicts_have_required_keys(self):
        result = research_augmented_retry(
            refinement_attempts=2,
            failure_info={"error_type": "FileNotFoundError", "message": "no such file"},
            base_prompt="Base.",
            feature_id="test-strategy-keys",
            attempt_number=2,
        )
        assert result["triggered"] is True
        for strategy in result["strategies"]:
            assert "title" in strategy
            assert "description" in strategy
            assert "priority" in strategy

    def test_triggers_at_refinement_attempts_greater_than_2(self):
        result = research_augmented_retry(
            refinement_attempts=5,
            failure_info={"error_type": "ImportError", "message": "cannot import bar"},
            base_prompt="Prompt.",
            feature_id="test-many-attempts",
            attempt_number=5,
        )
        assert result["triggered"] is True
