"""Test-writer sub-agent — single-AC failing test emission.

Exposes ``emit_failing_test``, a focused entry point that emits exactly one
failing pytest file for a single acceptance criterion.  Sits between the
spec-critic (F-R7-450) and the implementer sub-agent.

The TestGen-LLM triple filter (compile / fails-on-stub / coverage heuristic)
is re-exported here so callers can apply it without importing from the
orchestrator package directly.

Public API::

    from bob3.test_writer import emit_failing_test, triple_filter_one

    emitted = emit_failing_test(
        feature_id="abc123",
        ac_index=0,
        ac_text="File exists: src/bob3/mymod.py",
    )
    result = triple_filter_one(emitted)
    print(result.accepted)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.orchestrator.test_writer_agent import (
    BijectionReport,
    EmittedTest,
    FilterResult,
    _ac_id,
    _check_compiles,
    _check_fails_on_stub,
    _check_raises_coverage,
    _render_test,
    emit_failing_tests,
    generate_failing_tests,
    triple_filter,
    verify_bijection,
)

__all__ = [
    "emit_failing_test",
    "generate_failing_test",
    "triple_filter_one",
    "spawn_test_writer_subagent",
    "emit_failing_tests",
    "triple_filter",
    "verify_bijection",
    "generate_failing_tests",
    "filter_by_compilation",
    "filter_by_stub_pass",
    "filter_by_coverage",
    "EmittedTest",
    "FilterResult",
    "BijectionReport",
    "TestWriterSubagent",
]


class TestWriterSubagent:
    """Test-writer sub-agent: emits failing tests per AC before the implementer fires.

    Sits between the spec-critic (F-R7-450) and the implementer sub-agent.
    Calls generate_failing_tests to produce one failing pytest file per AC and
    applies the TestGen-LLM triple filter (compile / fails-on-stub / coverage).
    """

    def run(
        self,
        feature_id: str,
        acceptance_criteria: list[str],
        *,
        workspace: str | Path | None = None,
    ) -> dict[str, Any]:
        """Run the test-writer pipeline for a feature.

        Args:
            feature_id: Unique feature identifier (UUID or slug).
            acceptance_criteria: Ordered list of AC strings.
            workspace: Project root directory; defaults to ``Path.cwd()``.

        Returns:
            dict with keys: emitted, filter_results, bijection, gate_passed.

        Raises:
            ValueError: When feature_id is empty or acceptance_criteria is not a list.
        """
        return generate_failing_tests(
            feature_id,
            acceptance_criteria,
            workspace=workspace,
        )


def emit_failing_test(
    feature_id: str,
    ac_index: int,
    ac_text: str,
    *,
    workspace: str | Path | None = None,
) -> EmittedTest:
    """Emit a single failing pytest file for one acceptance criterion.

    Writes ``tests/<feature_id>/test_<ac_id>.py`` (creating intermediate
    directories and ``__init__.py`` as needed).  The generated test calls
    ``pytest.fail(...)`` unconditionally so it is guaranteed to be red before
    implementation.

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
    if not isinstance(feature_id, str) or not feature_id.strip():
        raise ValueError(
            f"feature_id must be a non-empty string, got {feature_id!r}"
        )
    if not isinstance(ac_text, str):
        raise ValueError(
            f"ac_text must be a string, got {type(ac_text).__name__!r}"
        )

    root = Path(workspace) if workspace else Path.cwd()
    out_dir = root / "tests" / feature_id
    out_dir.mkdir(parents=True, exist_ok=True)

    init = out_dir / "__init__.py"
    if not init.exists():
        init.write_text("", encoding="utf-8")

    ac_id = _ac_id(ac_index, ac_text)
    test_path = out_dir / f"test_{ac_id}.py"
    content = _render_test(feature_id, ac_index, ac_text, ac_id)
    test_path.write_text(content, encoding="utf-8")

    return EmittedTest(
        ac_index=ac_index,
        ac_id=ac_id,
        ac_text=ac_text,
        test_path=test_path,
        feature_id=feature_id,
    )


def triple_filter_one(
    emitted: EmittedTest,
    *,
    workspace: str | Path | None = None,
) -> FilterResult:
    """Apply the TestGen-LLM triple filter to a single emitted test.

    Convenience wrapper around ``triple_filter`` for the common case of
    filtering a single test.

    Args:
        emitted: The EmittedTest to filter.
        workspace: Project root directory; defaults to ``Path.cwd()``.

    Returns:
        FilterResult for the given test.

    Raises:
        ValueError: When ``emitted`` is not an EmittedTest instance.
    """
    if not isinstance(emitted, EmittedTest):
        raise ValueError(
            f"emitted must be an EmittedTest, got {type(emitted).__name__!r}"
        )
    results = triple_filter([emitted], workspace=workspace)
    return results[0]


def spawn_test_writer_subagent(
    feature_id: str,
    acceptance_criteria: list[str],
    *,
    workspace: str | Path | None = None,
) -> dict[str, Any]:
    """Spawn the test-writer sub-agent between spec-critic and implementer.

    Orchestrates the full test-writer pipeline for a feature:
    1. Emits one failing pytest file per acceptance criterion under
       ``tests/<feature_id>/test_<ac_id>.py``.
    2. Applies the TestGen-LLM triple filter (compile / fails-on-stub /
       coverage heuristic) to reject invalid tests.
    3. Verifies the AC↔test bijection (every AC has a test, every test
       maps to an AC).

    This function is the entry point called by the orchestrator between the
    spec-critic gate (F-R7-450) and the implementer sub-agent.

    Args:
        feature_id: Unique feature identifier (UUID or slug).
        acceptance_criteria: Ordered list of AC strings for this feature.
        workspace: Project root directory; defaults to ``Path.cwd()``.

    Returns:
        dict with keys:
            emitted: list[EmittedTest]
            filter_results: list[FilterResult]
            bijection: BijectionReport
            gate_passed: bool — True when all checks pass and bijection satisfied

    Raises:
        ValueError: When ``feature_id`` is empty or ``acceptance_criteria`` is not a list.
    """
    from bob3.orchestrator.test_writer_agent import generate_failing_tests

    return generate_failing_tests(
        feature_id,
        acceptance_criteria,
        workspace=workspace,
    )


def generate_failing_test(
    feature_id: str,
    ac_index: int,
    ac_text: str,
    *,
    workspace: str | Path | None = None,
) -> EmittedTest:
    """Generate one failing pytest file for a single acceptance criterion.

    Convenience wrapper around ``emit_failing_test`` that follows the
    TestGen-LLM naming convention.  Emits one red test under
    ``tests/<feature_id>/test_<ac_id>.py``.

    Args:
        feature_id: Unique feature identifier (UUID or filesystem-safe string).
        ac_index: Zero-based index of this AC within the feature's AC list.
        ac_text: The full acceptance criterion text.
        workspace: Project root directory; defaults to ``Path.cwd()``.

    Returns:
        EmittedTest metadata for the written file.

    Raises:
        ValueError: When ``feature_id`` is empty or ``ac_text`` is not a string.
    """
    return emit_failing_test(
        feature_id,
        ac_index,
        ac_text,
        workspace=workspace,
    )


def filter_by_compilation(emitted_tests: list[EmittedTest]) -> list[EmittedTest]:
    """Return only tests that compile without SyntaxError or ImportError.

    Applies the first check of the TestGen-LLM triple filter: AST-parses each
    test file and drops any that fail to compile.  Compiling tests are
    returned in input order.

    Args:
        emitted_tests: List of EmittedTest objects to filter.

    Returns:
        Subset of emitted_tests whose test files compile successfully.

    Raises:
        ValueError: When ``emitted_tests`` is not a list.
    """
    if not isinstance(emitted_tests, list):
        raise ValueError(
            f"emitted_tests must be a list, got {type(emitted_tests).__name__!r}"
        )
    return [et for et in emitted_tests if _check_compiles(et.test_path)]


def filter_by_stub_pass(emitted_tests: list[EmittedTest]) -> list[EmittedTest]:
    """Return only tests that correctly fail when run against stub (empty) code.

    Applies the second check of the TestGen-LLM triple filter: a test that
    mysteriously passes when no implementation exists is rejected.  Only tests
    that return a non-zero exit code in an isolated empty environment are kept.

    Args:
        emitted_tests: List of EmittedTest objects to filter.

    Returns:
        Subset of emitted_tests that fail on stub code (i.e. are genuinely red).

    Raises:
        ValueError: When ``emitted_tests`` is not a list.
    """
    if not isinstance(emitted_tests, list):
        raise ValueError(
            f"emitted_tests must be a list, got {type(emitted_tests).__name__!r}"
        )
    return [et for et in emitted_tests if _check_fails_on_stub(et.test_path)]


def filter_by_coverage(emitted_tests: list[EmittedTest]) -> list[EmittedTest]:
    """Return only tests that raise coverage of the AC-named region.

    Applies the third check of the TestGen-LLM triple filter: a test that
    imports or references no non-pytest symbols is rejected because it cannot
    exercise real implementation code.

    Args:
        emitted_tests: List of EmittedTest objects to filter.

    Returns:
        Subset of emitted_tests that reference at least one non-pytest symbol.

    Raises:
        ValueError: When ``emitted_tests`` is not a list.
    """
    if not isinstance(emitted_tests, list):
        raise ValueError(
            f"emitted_tests must be a list, got {type(emitted_tests).__name__!r}"
        )
    return [et for et in emitted_tests if _check_raises_coverage(et.test_path)]
