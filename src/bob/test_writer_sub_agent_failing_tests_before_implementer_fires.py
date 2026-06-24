"""Test-writer sub-agent — failing tests before implementer fires.

Inserts a test-writer sub-agent between spec-critic (F-R7-450) and the
implementer. Emits one failing pytest per AC ID under
``tests/<feature_id>/test_<ac_id>.py``. The TestGen-LLM Build/Pass/Coverage
triple filter rejects tests that don't compile, mysteriously pass on stub
code, or fail to raise coverage of the AC-named region.

Public API::

    from bob.test_writer_sub_agent_failing_tests_before_implementer_fires import (
        test_writer_sub_agent_failing_tests_before_implementer_fires,
    )

    result = test_writer_sub_agent_failing_tests_before_implementer_fires(
        feature_id="abc123",
        acceptance_criteria=["File exists: src/foo.py", "pytest: tests/test_foo.py"],
    )
    # result["emitted"] — list of EmittedTest objects
    # result["filter_results"] — list of FilterResult objects
    # result["bijection"] — BijectionReport
    # result["gate_passed"] — bool, True when all tests accepted by triple filter
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.orchestrator.test_writer_agent import (
    BijectionReport,
    EmittedTest,
    FilterResult,
    emit_failing_tests,
    triple_filter,
    verify_bijection,
)


def test_writer_sub_agent_failing_tests_before_implementer_fires(
    feature_id: str,
    acceptance_criteria: list[str],
    *,
    workspace: Path | None = None,
) -> dict[str, Any]:
    """Run the test-writer sub-agent pipeline for a feature before the implementer fires.

    Emits one failing pytest per acceptance criterion, applies the TestGen-LLM
    triple filter (compile / fails-on-stub / coverage heuristic), and verifies
    the AC↔test bijection.  Returns a summary dict so the orchestrator can
    gate the implementer on ``gate_passed``.

    Parameters
    ----------
    feature_id:
        Unique feature identifier — used as the subdirectory name under
        ``tests/`` and embedded in each emitted test file.
    acceptance_criteria:
        Ordered list of AC strings for this feature.
    workspace:
        Repository root directory; defaults to ``Path.cwd()``.

    Returns
    -------
    dict with keys:
        emitted: list[EmittedTest] — one per AC
        filter_results: list[FilterResult] — triple-filter result per emitted test
        bijection: BijectionReport — AC↔test bijection check
        gate_passed: bool — True when every emitted test is accepted by the filter
                            AND the bijection is satisfied
    """
    emitted: list[EmittedTest] = emit_failing_tests(
        feature_id,
        acceptance_criteria,
        workspace=workspace,
    )

    filter_results: list[FilterResult] = triple_filter(emitted, workspace=workspace)

    bijection: BijectionReport = verify_bijection(
        feature_id,
        acceptance_criteria,
        workspace=workspace,
    )

    all_accepted = all(r.accepted for r in filter_results)
    gate_passed = all_accepted and bijection.is_bijective

    return {
        "emitted": emitted,
        "filter_results": filter_results,
        "bijection": bijection,
        "gate_passed": gate_passed,
    }
