"""Tests for failure classification system."""

import pytest
from datetime import datetime

from bob.models.base import FailureType, Task, TaskStatus
from bob.orchestrator.failure_classifier import (
    ClassificationResult,
    analyze_task_complexity,
    check_repeated_errors,
    classify_by_patterns,
    classify_failure,
    generate_diagnosis_prompt,
)


# Test Data Fixtures


@pytest.fixture
def simple_task():
    """Create a simple task with minimal complexity."""
    return Task(
        id="task-simple",
        project_id="proj-123",
        spec_id="F001",
        title="Simple feature",
        description="A simple feature with few steps",
        status=TaskStatus.PENDING,
        steps=["Step 1", "Step 2"],
        depends_on=[],
    )


@pytest.fixture
def complex_task():
    """Create a complex task with many steps and dependencies."""
    return Task(
        id="task-complex",
        project_id="proj-123",
        spec_id="F042",
        title="Complex feature",
        description=(
            "This is a very complex feature that requires multiple "
            "components and various integrations with all systems. "
            "It needs complete implementation across every module."
        ),
        status=TaskStatus.PENDING,
        steps=[f"Step {i}" for i in range(1, 12)],
        depends_on=["F001", "F002", "F003", "F004", "F005", "F006"],
    )


# Test Pattern Classification


class TestClassifyByPatterns:
    """Test pattern-based error classification."""

    def test_infrastructure_missing_module(self):
        """Test detection of missing module errors."""
        errors = ["ModuleNotFoundError: No module named 'requests'"]
        result = classify_by_patterns(errors)

        assert result is not None
        assert result.failure_type == FailureType.WRONG_INFRA
        assert result.confidence >= 0.8
        assert "infrastructure" in result.reason.lower()
        assert result.research_queries == []  # No research for infra

    def test_infrastructure_command_not_found(self):
        """Test detection of missing command errors."""
        errors = ["bash: docker: command not found"]
        result = classify_by_patterns(errors)

        assert result is not None
        assert result.failure_type == FailureType.WRONG_INFRA
        assert "missing_command" in result.details["pattern_type"]

    def test_infrastructure_permission_denied(self):
        """Test detection of permission errors."""
        errors = ["PermissionError: [Errno 13] Permission denied: '/etc/config'"]
        result = classify_by_patterns(errors)

        assert result is not None
        assert result.failure_type == FailureType.WRONG_INFRA

    def test_complexity_timeout(self):
        """Test detection of timeout errors."""
        errors = ["TimeoutError: Test execution exceeded timeout limit"]
        result = classify_by_patterns(errors)

        assert result is not None
        assert result.failure_type == FailureType.TOO_BIG
        assert "complex" in result.reason.lower()

    def test_complexity_recursion(self):
        """Test detection of recursion errors."""
        errors = ["RecursionError: maximum recursion depth exceeded"]
        result = classify_by_patterns(errors)

        assert result is not None
        assert result.failure_type == FailureType.TOO_BIG

    def test_missing_info_attribute_error(self):
        """Test detection of unknown attribute errors."""
        errors = ["AttributeError: 'dict' has no attribute 'append'"]
        result = classify_by_patterns(errors)

        assert result is not None
        assert result.failure_type == FailureType.MISSING_INFO
        assert len(result.research_queries) > 0
        assert "append" in result.research_queries[0].lower()

    def test_missing_info_api_mismatch(self):
        """Test detection of API signature mismatches."""
        errors = ["TypeError: open() got an unexpected keyword argument 'encoding'"]
        result = classify_by_patterns(errors)

        assert result is not None
        assert result.failure_type == FailureType.MISSING_INFO
        assert "api_mismatch" in result.details["pattern_type"]

    def test_bad_assumptions_assertion(self):
        """Test detection of assertion failures."""
        errors = ["AssertionError: Expected 5 but got 3"]
        result = classify_by_patterns(errors)

        assert result is not None
        assert result.failure_type == FailureType.BAD_ASSUMPTIONS
        assert "assertion_failed" in result.details["pattern_type"]

    def test_bad_assumptions_key_error(self):
        """Test detection of KeyError."""
        errors = ["KeyError: 'user_id'"]
        result = classify_by_patterns(errors)

        assert result is not None
        assert result.failure_type == FailureType.BAD_ASSUMPTIONS

    def test_no_pattern_match(self):
        """Test when no pattern matches."""
        errors = ["Some random error message"]
        result = classify_by_patterns(errors)

        assert result is None

    def test_case_insensitive_matching(self):
        """Test that pattern matching is case-insensitive."""
        errors = ["modulenotfounderror: no module named 'REQUESTS'"]
        result = classify_by_patterns(errors)

        assert result is not None
        assert result.failure_type == FailureType.WRONG_INFRA


# Test Research Query Generation


class TestResearchQueries:
    """Test research query generation."""

    def test_queries_for_deprecated_api(self):
        """Test query generation for deprecated APIs."""
        errors = ["DeprecationWarning: old_function is deprecated"]
        result = classify_by_patterns(errors)

        assert result is not None
        assert len(result.research_queries) > 0
        assert "deprecated" in result.research_queries[0].lower()
        assert "2026" in result.research_queries[0]

    def test_queries_for_unknown_attribute(self):
        """Test query generation for unknown attributes."""
        errors = ["AttributeError: module has no attribute 'new_method'"]
        result = classify_by_patterns(errors)

        assert result is not None
        assert "new_method" in result.research_queries[0].lower()

    def test_queries_include_error_class(self):
        """Test that queries include error class names."""
        errors = ["ValueError: invalid literal for int()"]
        result = classify_by_patterns(errors)

        # Should classify as BAD_ASSUMPTIONS and have queries
        if result:
            assert len(result.research_queries) > 0


# Test Repeated Error Detection


class TestCheckRepeatedErrors:
    """Test repeated error detection."""

    def test_no_repeated_errors_empty(self):
        """Test with no error history."""
        is_repeated, pattern = check_repeated_errors([])

        assert is_repeated is False
        assert pattern is None

    def test_no_repeated_errors_too_few(self):
        """Test with too few errors to determine repetition."""
        errors = [{"error_msg": "Error 1"}]
        is_repeated, pattern = check_repeated_errors(errors)

        assert is_repeated is False
        assert pattern is None

    def test_repeated_same_error(self):
        """Test detection of repeated identical errors."""
        errors = [
            {"error_msg": "KeyError: 'user_id' at line 42"},
            {"error_msg": "KeyError: 'user_id' at line 42"},
            {"error_msg": "KeyError: 'user_id' at line 42"},
        ]
        is_repeated, pattern = check_repeated_errors(errors)

        assert is_repeated is True
        assert pattern is not None
        assert "keyerror" in pattern.lower()

    def test_normalized_error_comparison(self):
        """Test that errors are normalized for comparison."""
        errors = [
            {"error_msg": "Error at line 42 in /home/user/file.py"},
            {"error_msg": "Error at line 123 in /home/other/file.py"},
            {"error_msg": "Error at line 456 in /var/lib/file.py"},
        ]
        is_repeated, pattern = check_repeated_errors(errors)

        # After normalization, these should be the same
        assert is_repeated is True

    def test_different_errors_not_repeated(self):
        """Test that different errors are not marked as repeated."""
        errors = [
            {"error_msg": "KeyError: 'user_id'"},
            {"error_msg": "ValueError: invalid value"},
            {"error_msg": "TypeError: wrong type"},
        ]
        is_repeated, pattern = check_repeated_errors(errors)

        assert is_repeated is False

    def test_handles_missing_error_msg(self):
        """Test handling of records without error_msg."""
        errors = [
            {"timestamp": "2026-01-01"},
            {"error_msg": "Error 1"},
            {},
            {"error_msg": "Error 1"},
        ]
        is_repeated, pattern = check_repeated_errors(errors)

        # Should still detect repetition of "Error 1"
        assert is_repeated is True


# Test Task Complexity Analysis


class TestAnalyzeTaskComplexity:
    """Test task complexity analysis."""

    def test_simple_task_low_complexity(self, simple_task):
        """Test that simple tasks have low complexity scores."""
        result = analyze_task_complexity(simple_task)

        assert result["complexity_score"] < 4
        assert result["is_complex"] is False
        assert result["should_decompose"] is False

    def test_complex_task_high_complexity(self, complex_task):
        """Test that complex tasks have high complexity scores."""
        result = analyze_task_complexity(complex_task)

        assert result["complexity_score"] >= 4
        assert result["is_complex"] is True
        assert len(result["reasons"]) > 0

    def test_complexity_from_many_steps(self, simple_task):
        """Test complexity detection from step count."""
        simple_task.steps = [f"Step {i}" for i in range(1, 12)]
        result = analyze_task_complexity(simple_task)

        assert result["complexity_score"] > 0
        assert any("steps" in r.lower() for r in result["reasons"])

    def test_complexity_from_many_dependencies(self, simple_task):
        """Test complexity detection from dependency count."""
        simple_task.depends_on = ["F001", "F002", "F003", "F004", "F005", "F006"]
        result = analyze_task_complexity(simple_task)

        assert result["complexity_score"] > 0
        assert any("dependencies" in r.lower() for r in result["reasons"])

    def test_complexity_from_long_description(self, simple_task):
        """Test complexity detection from description length."""
        simple_task.description = "x" * 600
        result = analyze_task_complexity(simple_task)

        assert result["complexity_score"] > 0
        assert any("description" in r.lower() for r in result["reasons"])

    def test_complexity_from_keywords(self, simple_task):
        """Test complexity detection from complexity keywords."""
        simple_task.description = "Complete all complex multiple various features"
        result = analyze_task_complexity(simple_task)

        assert result["complexity_score"] > 0
        assert any("keyword" in r.lower() for r in result["reasons"])

    def test_should_decompose_threshold(self, complex_task):
        """Test that high complexity triggers decomposition recommendation."""
        result = analyze_task_complexity(complex_task)

        # Complex task should exceed decomposition threshold
        assert result["should_decompose"] is True


# Test Comprehensive Failure Classification


class TestClassifyFailure:
    """Test comprehensive failure classification."""

    def test_classify_infrastructure_error(self, simple_task):
        """Test classification of infrastructure errors."""
        error_history = [
            {"error_msg": "ModuleNotFoundError: No module named 'requests'"}
        ]
        deps_status = {}

        result = classify_failure(simple_task, error_history, deps_status)

        assert result.failure_type == FailureType.WRONG_INFRA
        assert result.confidence >= 0.8

    def test_classify_repeated_error_as_bad_assumptions(self, simple_task):
        """Test that repeated errors escalate to BAD_ASSUMPTIONS."""
        error_history = [
            {"error_msg": "KeyError: 'user_id' at line 42"},
            {"error_msg": "KeyError: 'user_id' at line 43"},
            {"error_msg": "KeyError: 'user_id' at line 44"},
        ]
        deps_status = {}

        result = classify_failure(simple_task, error_history, deps_status)

        assert result.failure_type == FailureType.BAD_ASSUMPTIONS
        assert "repeating" in result.reason.lower()

    def test_classify_complex_task_with_errors(self, complex_task):
        """Test that complex tasks with errors are marked for decomposition."""
        error_history = [{"error_msg": "ValueError: something went wrong"}]
        deps_status = {}

        result = classify_failure(complex_task, error_history, deps_status)

        # Should prioritize decomposition for complex tasks
        assert result.failure_type == FailureType.TOO_BIG

    def test_classify_complex_task_no_errors(self, complex_task):
        """Test classification of complex task without errors."""
        error_history = []
        deps_status = {}

        result = classify_failure(complex_task, error_history, deps_status)

        # Should suggest research or report missing info
        assert result.failure_type in [
            FailureType.TOO_BIG,
            FailureType.MISSING_INFO,
        ]

    def test_classify_unclassifiable_error(self, simple_task):
        """Test classification of unrecognized error patterns."""
        error_history = [{"error_msg": "Something strange happened"}]
        deps_status = {}

        result = classify_failure(simple_task, error_history, deps_status)

        assert result.failure_type == FailureType.NEEDS_RESEARCH
        assert result.confidence < 0.7
        assert len(result.research_queries) > 0

    def test_classify_no_errors(self, simple_task):
        """Test classification when task fails without errors."""
        error_history = []
        deps_status = {}

        result = classify_failure(simple_task, error_history, deps_status)

        assert result.failure_type == FailureType.MISSING_INFO
        assert result.confidence < 0.5
        assert "without clear error" in result.reason.lower()

    def test_classify_timeout_error(self, simple_task):
        """Test classification of timeout errors."""
        error_history = [{"error_msg": "TimeoutError: execution exceeded limit"}]
        deps_status = {}

        result = classify_failure(simple_task, error_history, deps_status)

        assert result.failure_type == FailureType.TOO_BIG
        assert "timeout" in result.details["pattern_type"]

    def test_classify_deprecated_api(self, simple_task):
        """Test classification of deprecated API usage."""
        error_history = [{"error_msg": "DeprecationWarning: function_x is deprecated"}]
        deps_status = {}

        result = classify_failure(simple_task, error_history, deps_status)

        assert result.failure_type == FailureType.MISSING_INFO
        assert len(result.research_queries) > 0
        assert "deprecated" in result.research_queries[0].lower()


# Test Diagnosis Prompt Generation


class TestGenerateDiagnosisPrompt:
    """Test diagnosis prompt generation."""

    def test_prompt_includes_task_info(self, simple_task):
        """Test that prompt includes task information."""
        error_history = [{"error_msg": "Some error"}]
        classification = ClassificationResult(
            failure_type=FailureType.NEEDS_RESEARCH,
            confidence=0.5,
            reason="Unknown error",
            research_queries=["Query 1"],
            recommended_action="Research",
            details={},
        )

        prompt = generate_diagnosis_prompt(simple_task, error_history, classification)

        assert simple_task.spec_id in prompt
        assert simple_task.title in prompt
        assert simple_task.description in prompt

    def test_prompt_includes_error_history(self, simple_task):
        """Test that prompt includes error history."""
        error_history = [
            {"timestamp": "2026-01-01", "error_msg": "Error 1"},
            {"timestamp": "2026-01-02", "error_msg": "Error 2"},
        ]
        classification = ClassificationResult(
            failure_type=FailureType.NEEDS_RESEARCH,
            confidence=0.5,
            reason="Unknown",
            research_queries=[],
            recommended_action="Research",
            details={},
        )

        prompt = generate_diagnosis_prompt(simple_task, error_history, classification)

        assert "Error 1" in prompt
        assert "Error 2" in prompt

    def test_prompt_includes_classification(self, simple_task):
        """Test that prompt includes initial classification."""
        error_history = [{"error_msg": "Error"}]
        classification = ClassificationResult(
            failure_type=FailureType.TOO_BIG,
            confidence=0.85,
            reason="Task is too complex",
            research_queries=[],
            recommended_action="Decompose",
            details={},
        )

        prompt = generate_diagnosis_prompt(simple_task, error_history, classification)

        assert "TOO_BIG" in prompt
        assert "85%" in prompt
        assert "Task is too complex" in prompt

    def test_prompt_includes_categories(self, simple_task):
        """Test that prompt includes all failure categories."""
        error_history = []
        classification = ClassificationResult(
            failure_type=FailureType.NEEDS_RESEARCH,
            confidence=0.5,
            reason="Test",
            research_queries=[],
            recommended_action="Test",
            details={},
        )

        prompt = generate_diagnosis_prompt(simple_task, error_history, classification)

        assert "TOO_BIG" in prompt
        assert "MISSING_INFO" in prompt
        assert "WRONG_INFRA" in prompt
        assert "BAD_ASSUMPTIONS" in prompt
        assert "NEEDS_RESEARCH" in prompt

    def test_prompt_truncates_long_errors(self, simple_task):
        """Test that very long error messages are truncated."""
        long_error = "x" * 500
        error_history = [{"error_msg": long_error}]
        classification = ClassificationResult(
            failure_type=FailureType.NEEDS_RESEARCH,
            confidence=0.5,
            reason="Test",
            research_queries=[],
            recommended_action="Test",
            details={},
        )

        prompt = generate_diagnosis_prompt(simple_task, error_history, classification)

        # Should truncate at 300 chars
        assert long_error[:300] in prompt
        assert len(prompt) < 1500  # Prompt shouldn't be too long


# Test Edge Cases


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_error_messages(self, simple_task):
        """Test handling of empty error messages."""
        error_history = [{"error_msg": ""}, {"error_msg": None}, {}]
        deps_status = {}

        result = classify_failure(simple_task, error_history, deps_status)

        assert result is not None
        assert result.failure_type == FailureType.MISSING_INFO

    def test_task_with_no_steps(self):
        """Test handling of task with no steps."""
        task = Task(
            id="task-nosteps",
            project_id="proj-123",
            spec_id="F999",
            title="No steps",
            description="",
            status=TaskStatus.PENDING,
            steps=[],
            depends_on=[],
        )

        result = analyze_task_complexity(task)

        assert result["complexity_score"] == 0
        assert result["is_complex"] is False

    def test_task_with_empty_description(self):
        """Test handling of task with no description."""
        task = Task(
            id="task-nodesc",
            project_id="proj-123",
            spec_id="F999",
            title="No description",
            description="",
            status=TaskStatus.PENDING,
        )

        result = analyze_task_complexity(task)

        assert result is not None

    def test_very_long_error_messages(self, simple_task):
        """Test handling of very long error messages."""
        long_error = "Error: " + "x" * 10000
        error_history = [{"error_msg": long_error}]
        deps_status = {}

        result = classify_failure(simple_task, error_history, deps_status)

        # Should handle without crashing
        assert result is not None

    def test_special_characters_in_errors(self, simple_task):
        """Test handling of special characters in error messages."""
        error_history = [{"error_msg": "Error with 特殊字符 and émojis 🚀"}]
        deps_status = {}

        result = classify_failure(simple_task, error_history, deps_status)

        assert result is not None
