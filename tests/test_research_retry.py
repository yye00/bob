"""Tests for research_retry — spawn_research_agent, classify_failure, inject_strategies.

AC: pytest: tests/test_research_retry.py
Feature: Research-augmented retry — path-finding on ambiguous AC failure
"""

from __future__ import annotations

import pytest

from bob.research_retry import (
    classify_failure,
    inject_strategies,
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

    def test_empty_dict_returns_unknown(self):
        result = classify_failure({})
        assert result == "unknown"

    def test_non_dict_raises_value_error(self):
        with pytest.raises(ValueError):
            classify_failure("not a dict")

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            classify_failure(None)

    def test_invalid_explicit_failure_class_raises_value_error(self):
        with pytest.raises(ValueError, match="failure_class"):
            classify_failure({"failure_class": "not_valid"})


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

    def test_invalid_class_raises_value_error(self):
        with pytest.raises(ValueError, match="not a valid failure class"):
            spawn_research_agent("bogus_class")

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            spawn_research_agent(None)

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            spawn_research_agent("")


class TestInjectStrategies:
    def test_returns_string(self):
        result = inject_strategies(
            base_prompt="Implement the feature.",
            failure_class="import_error",
            attempt_number=2,
        )
        assert isinstance(result, str)

    def test_contains_base_prompt(self):
        result = inject_strategies(
            base_prompt="Implement the feature.",
            failure_class="import_error",
            attempt_number=2,
        )
        assert "Implement the feature." in result

    def test_contains_strategies_for_classifiable_failure(self):
        result = inject_strategies(
            base_prompt="Prompt.",
            failure_class="import_error",
            attempt_number=2,
        )
        assert "Research-Augmented Retry" in result

    def test_unknown_failure_class_returns_base_prompt_unchanged(self):
        result = inject_strategies(
            base_prompt="Prompt.",
            failure_class="unknown",
            attempt_number=2,
        )
        assert result == "Prompt."

    def test_attempt_number_appears_in_output(self):
        result = inject_strategies(
            base_prompt="Prompt.",
            failure_class="import_error",
            attempt_number=5,
        )
        assert "5" in result

    def test_invalid_failure_class_raises_value_error(self):
        with pytest.raises(ValueError):
            inject_strategies(
                base_prompt="Prompt.",
                failure_class="not_valid_class",
                attempt_number=2,
            )

    def test_empty_base_prompt_does_not_raise_for_unknown(self):
        result = inject_strategies(
            base_prompt="",
            failure_class="unknown",
            attempt_number=1,
        )
        assert result == ""

    def test_returns_augmented_prompt_with_strategies_for_ambiguous_ac(self):
        result = inject_strategies(
            base_prompt="Implement.",
            failure_class="ambiguous_ac",
            attempt_number=3,
        )
        assert "ambiguous_ac" in result
        assert "Implement." in result
