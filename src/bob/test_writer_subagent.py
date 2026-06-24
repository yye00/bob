"""Test-writer sub-agent — failing tests before implementer fires.

Public facade over ``bob.orchestrator.test_writer_agent``.  Provides
``generate_failing_tests`` as the canonical entry point for the test-writer
sub-agent, which sits between the spec-critic (F-R7-450) and the implementer.

The agent emits one failing pytest per AC ID under
``tests/<feature_id>/test_<ac_id>.py``.  The TestGen-LLM Build/Pass/Coverage
triple filter rejects tests that don't compile, mysteriously pass on stub
code, or fail to raise coverage of the AC-named region.

Usage::

    from bob.test_writer_subagent import generate_failing_tests

    result = generate_failing_tests(
        feature_id="abc123",
        acceptance_criteria=["File exists: src/foo.py", "pytest: tests/test_foo.py"],
    )
    # result["emitted"]        — list[EmittedTest]
    # result["filter_results"] — list[FilterResult]
    # result["bijection"]      — BijectionReport
    # result["gate_passed"]    — bool
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.orchestrator.test_writer_agent import (
    BijectionReport,
    EmittedTest,
    FilterResult,
    emit_failing_test as _emit_failing_test,
    generate_failing_tests as _generate_failing_tests,
)

__all__ = [
    "generate_failing_tests",
    "emit_failing_test",
    "BijectionReport",
    "EmittedTest",
    "FilterResult",
]


def emit_failing_test(
    feature_id: str,
    ac_index: int,
    ac_text: str,
    *,
    workspace: "str | Path | None" = None,
) -> "EmittedTest":
    """Emit a single failing pytest file for one acceptance criterion.

    Public facade over ``bob.orchestrator.test_writer_agent.emit_failing_test``.

    Args:
        feature_id: Unique feature identifier (UUID or any filesystem-safe string).
        ac_index: Zero-based index of this AC within the feature's AC list.
        ac_text: The full acceptance criterion text.
        workspace: Project root directory; defaults to ``Path.cwd()``.

    Returns:
        EmittedTest metadata for the written file.

    Raises:
        ValueError: When ``feature_id`` is empty or ``ac_text`` is not a string.
    """
    return _emit_failing_test(feature_id, ac_index, ac_text, workspace=workspace)


def generate_failing_tests(
    feature_id: str,
    acceptance_criteria: list[str],
    *,
    workspace: "str | Path | None" = None,
) -> dict[str, Any]:
    """Generate one failing pytest per acceptance criterion before the implementer fires.

    Delegates to the full test-writer pipeline in
    ``bob.orchestrator.test_writer_agent``:
    1. ``emit_failing_tests`` — write one test file per AC under
       ``tests/<feature_id>/test_<ac_id>.py``
    2. ``triple_filter`` — reject tests that don't compile, pass on stub, or
       lack coverage of the AC-named region
    3. ``verify_bijection`` — confirm that every AC has exactly one test file
       and every test file maps back to a declared AC

    The orchestrator gates the implementer on ``gate_passed``.

    Args:
        feature_id: Unique feature identifier (UUID or any filesystem-safe
            string).  Must be non-empty and non-whitespace.
        acceptance_criteria: Ordered list of AC strings for this feature.
            Must be a list (may be empty).
        workspace: Project root directory.  Defaults to ``Path.cwd()``.

    Returns:
        dict with keys:
            emitted:        list[EmittedTest] — one per AC
            filter_results: list[FilterResult] — triple-filter result per test
            bijection:      BijectionReport — AC↔test bijection check
            gate_passed:    bool — True when all triple-filter checks pass and
                            the bijection is satisfied

    Raises:
        ValueError: When ``feature_id`` is empty/whitespace or
            ``acceptance_criteria`` is not a list.
    """
    return _generate_failing_tests(
        feature_id,
        acceptance_criteria,
        workspace=workspace,
    )
