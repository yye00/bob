"""Tests for research_augmented_retry_path_finding_ambiguous_ac_failure."""

import pathlib

import pytest

from bob.research_augmented_retry_path_finding_ambiguous_ac_failure import (
    research_augmented_retry_path_finding_ambiguous_ac_failure,
)


def test_research_augmented_retry_path_finding_ambiguous_ac_failure():
    """Core AC test: function exists, runs, and returns a valid result dict."""
    result = research_augmented_retry_path_finding_ambiguous_ac_failure(
        refinement_attempts=0,
        failure_info={"error_type": "ImportError", "message": "cannot import name foo"},
        base_prompt="Implement the feature.",
        feature_id="test-feature-123",
        attempt_number=1,
    )
    assert isinstance(result, dict)
    assert "triggered" in result
    assert "failure_class" in result
    assert "strategies" in result
    assert "prompt" in result
    assert "strategies_path" in result
    assert "prompt_path" in result


def test_does_not_trigger_below_threshold():
    """Should not trigger when refinement_attempts < 2."""
    result = research_augmented_retry_path_finding_ambiguous_ac_failure(
        refinement_attempts=1,
        failure_info={"error_type": "ImportError", "message": "cannot import name foo"},
        base_prompt="Implement the feature.",
        feature_id="test-feature-abc",
        attempt_number=1,
    )
    assert result["triggered"] is False
    assert result["strategies"] == []
    assert result["prompt"] == "Implement the feature."
    assert result["strategies_path"] is None
    assert result["prompt_path"] is None


def test_triggers_at_threshold_with_classifiable_failure():
    """Should trigger when refinement_attempts >= 2 and failure is classifiable."""
    result = research_augmented_retry_path_finding_ambiguous_ac_failure(
        refinement_attempts=2,
        failure_info={"error_type": "ImportError", "message": "cannot import name foo"},
        base_prompt="Implement the feature.",
        feature_id="test-feature-trigger",
        attempt_number=2,
    )
    assert result["triggered"] is True
    assert result["failure_class"] == "import_error"
    assert len(result["strategies"]) > 0
    assert result["prompt"] != "Implement the feature."
    assert "Research-Augmented Retry" in result["prompt"]


def test_does_not_trigger_on_unknown_failure_class():
    """Unknown failure class should not trigger even at >= 2 attempts."""
    result = research_augmented_retry_path_finding_ambiguous_ac_failure(
        refinement_attempts=3,
        failure_info={"error_type": "SomeWeirdError", "message": "completely unrecognized"},
        base_prompt="Implement the feature.",
        feature_id="test-feature-unknown",
        attempt_number=3,
    )
    assert result["triggered"] is False
    assert result["failure_class"] == "unknown"
    assert result["strategies"] == []


def test_classifies_missing_test_file_failure():
    """Should classify and surface strategies for missing_test_file failure."""
    result = research_augmented_retry_path_finding_ambiguous_ac_failure(
        refinement_attempts=2,
        failure_info={"error_type": "FileNotFoundError", "message": "no such file"},
        base_prompt="Base prompt.",
        feature_id="test-feature-missing-file",
        attempt_number=2,
    )
    assert result["triggered"] is True
    assert result["failure_class"] == "missing_test_file"
    assert len(result["strategies"]) >= 1
    for strategy in result["strategies"]:
        assert "title" in strategy
        assert "description" in strategy
        assert "priority" in strategy


def test_classifies_ambiguous_ac_failure():
    """Should classify and surface strategies for ambiguous_ac failure."""
    result = research_augmented_retry_path_finding_ambiguous_ac_failure(
        refinement_attempts=2,
        failure_info={"message": "ambiguous acceptance criteria, unclear"},
        base_prompt="Implement ambiguous feature.",
        feature_id="test-feature-ambiguous",
        attempt_number=2,
    )
    assert result["triggered"] is True
    assert result["failure_class"] == "ambiguous_ac"
    assert len(result["strategies"]) >= 1


def test_persists_strategies_and_prompt_when_triggered(tmp_path):
    """When triggered, should write strategies YAML and prompt file to disk."""
    result = research_augmented_retry_path_finding_ambiguous_ac_failure(
        refinement_attempts=2,
        failure_info={"error_type": "ImportError", "message": "cannot import foo"},
        base_prompt="Base prompt text.",
        feature_id="test-persist-feature",
        attempt_number=2,
        workspace=tmp_path,
    )
    assert result["triggered"] is True
    assert result["strategies_path"] is not None
    assert result["prompt_path"] is not None

    strategies_path = pathlib.Path(result["strategies_path"])
    assert strategies_path.exists()
    assert strategies_path.suffix == ".yaml"

    prompt_path = pathlib.Path(result["prompt_path"])
    assert prompt_path.exists()
    content = prompt_path.read_text()
    assert "Base prompt text." in content
    assert "Research-Augmented Retry" in content


def test_prompt_contains_strategy_titles_when_triggered():
    """Injected prompt should contain the strategy title for the failure class."""
    result = research_augmented_retry_path_finding_ambiguous_ac_failure(
        refinement_attempts=3,
        failure_info={"error_type": "TypeError", "message": "type mismatch"},
        base_prompt="Original implementation prompt.",
        feature_id="test-prompt-injection",
        attempt_number=3,
    )
    assert result["triggered"] is True
    assert result["failure_class"] == "type_mismatch"
    for strategy in result["strategies"]:
        assert strategy["title"] in result["prompt"]


def test_explicit_failure_class_key_takes_precedence():
    """Explicit failure_class key in failure_info should be used directly."""
    result = research_augmented_retry_path_finding_ambiguous_ac_failure(
        refinement_attempts=2,
        failure_info={"failure_class": "empty_impl"},
        base_prompt="Implement with TDD.",
        feature_id="test-explicit-class",
        attempt_number=2,
    )
    assert result["triggered"] is True
    assert result["failure_class"] == "empty_impl"
    assert len(result["strategies"]) > 0
