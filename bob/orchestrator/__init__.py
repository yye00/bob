"""Orchestrator components for BOB framework.

This module provides task orchestration, scheduling, and escalation logic.
"""

from .escalation import EscalationController, MAX_ATTEMPTS_PER_MODEL, MAX_DIAGNOSIS_ATTEMPTS
from .failure_classifier import (
    ClassificationResult,
    analyze_task_complexity,
    check_repeated_errors,
    classify_by_patterns,
    classify_failure,
    generate_diagnosis_prompt,
)
from .task_decomposer import (
    TaskDecomposer,
    SubTask,
    DecompositionResult,
    generate_decomposition_prompt,
    analyze_task_for_decomposition,
    validate_decomposition,
    suggest_decomposition,
)
from .task_queue import TaskQueue

__all__ = [
    "EscalationController",
    "MAX_ATTEMPTS_PER_MODEL",
    "MAX_DIAGNOSIS_ATTEMPTS",
    "TaskQueue",
    "ClassificationResult",
    "analyze_task_complexity",
    "check_repeated_errors",
    "classify_by_patterns",
    "classify_failure",
    "generate_diagnosis_prompt",
    "TaskDecomposer",
    "SubTask",
    "DecompositionResult",
    "generate_decomposition_prompt",
    "analyze_task_for_decomposition",
    "validate_decomposition",
    "suggest_decomposition",
]
