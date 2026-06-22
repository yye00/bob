"""Test-writer sub-agent public API — TestWriterAgent facade.

Wraps ``bob3.orchestrator.test_writer_agent`` with an object-oriented API
so orchestrators and callers can instantiate ``TestWriterAgent`` and call
``generate`` / ``filter`` / ``validate`` as named methods.

Usage::

    from test_writer import TestWriterAgent

    agent = TestWriterAgent(workspace=".")
    result = agent.generate(feature_id="abc123", acceptance_criteria=["File exists: src/x.py"])
    # result["gate_passed"] is True when all triple-filter checks pass
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.orchestrator.test_writer_agent import (
    BijectionReport,
    EmittedTest,
    FilterResult,
    emit_failing_tests,
    generate_failing_tests,
    triple_filter,
    verify_bijection,
)


class TestWriterAgent:
    """Object-oriented facade over the test-writer sub-agent pipeline.

    Inserts between the spec-critic and the implementer sub-agent.  For each
    acceptance criterion it emits one failing pytest file, applies the
    TestGen-LLM triple filter (compile / fails-on-stub / coverage heuristic),
    and verifies the AC↔test bijection.

    Args:
        workspace: Project root directory.  Defaults to the current working
                   directory when ``None``.
    """

    def __init__(self, workspace: str | Path | None = None) -> None:
        self.workspace = Path(workspace) if workspace else None

    def generate(
        self,
        feature_id: str,
        acceptance_criteria: list[str],
    ) -> dict[str, Any]:
        """Run the full test-writer pipeline.

        Emits one failing pytest per AC, applies the triple filter, and
        verifies the AC↔test bijection.

        Args:
            feature_id: Unique feature identifier (UUID or slug).
            acceptance_criteria: Ordered list of AC strings for this feature.

        Returns:
            dict with keys:
                emitted: list[EmittedTest]
                filter_results: list[FilterResult]
                bijection: BijectionReport
                gate_passed: bool

        Raises:
            ValueError: When ``feature_id`` is empty or ``acceptance_criteria``
                        is not a list.
        """
        return generate_failing_tests(
            feature_id,
            acceptance_criteria,
            workspace=self.workspace,
        )

    def emit(
        self,
        feature_id: str,
        acceptance_criteria: list[str],
    ) -> list[EmittedTest]:
        """Emit one failing test file per acceptance criterion.

        Args:
            feature_id: Unique feature identifier.
            acceptance_criteria: Ordered list of AC strings.

        Returns:
            List of EmittedTest objects (one per AC).
        """
        return emit_failing_tests(feature_id, acceptance_criteria, workspace=self.workspace)

    def filter(self, emitted_tests: list[EmittedTest]) -> list[FilterResult]:
        """Apply the TestGen-LLM triple filter to a list of emitted tests.

        Args:
            emitted_tests: List of EmittedTest objects from ``emit``.

        Returns:
            List of FilterResult objects (one per input test).
        """
        return triple_filter(emitted_tests, workspace=self.workspace)

    def validate(
        self,
        feature_id: str,
        acceptance_criteria: list[str],
    ) -> BijectionReport:
        """Verify a bijection between ACs and emitted test files.

        Args:
            feature_id: Feature identifier.
            acceptance_criteria: Declared list of AC strings.

        Returns:
            BijectionReport with ``is_bijective=True`` when no missing or
            orphan tests were found.
        """
        return verify_bijection(feature_id, acceptance_criteria, workspace=self.workspace)
