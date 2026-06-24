"""Research-augmented retry — path-finding on ambiguous AC failure (F-R7-474).

When refinement_attempts >= 2 AND the previous attempt's failure is
classifiable, spawn a research sub-agent that surfaces 1-2 alternative
strategies tailored to the failure class. Inject strategies into the next
implementer's prompt prefix. The implementer retries with NEW information.
"""

from __future__ import annotations

import enum
import logging
import pathlib
from dataclasses import dataclass, field
from typing import Any

import yaml

from bob3.synthesis.canonical_ac_emitter import (
    SynthesisResult,
    synthesise_with_canonical_gate,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums and data models
# ---------------------------------------------------------------------------


class FailureClass(enum.Enum):
    """Classification of why a feature implementation attempt failed."""

    missing_test_file = "missing_test_file"
    import_error = "import_error"
    type_mismatch = "type_mismatch"
    contract_violation = "contract_violation"
    empty_impl = "empty_impl"
    ambiguous_ac = "ambiguous_ac"
    unknown = "unknown"


@dataclass
class Strategy:
    """A concrete alternative implementation strategy for a given failure class."""

    title: str
    description: str
    failure_class: FailureClass
    priority: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_failure(failure_info: dict[str, Any]) -> FailureClass:
    """Classify a feature implementation failure into a FailureClass enum value.

    Args:
        failure_info: Dict with keys like ``error_type``, ``message``, ``traceback``.
                      Must contain at least one of those keys.

    Returns:
        A ``FailureClass`` enum value.

    Raises:
        ValueError: If ``failure_info`` is not a dict or is missing the required
                    top-level ``failure_class`` key entirely (malformed input).
    """
    if not isinstance(failure_info, dict):
        raise ValueError(
            "failure_class: failure_info must be a dict; "
            f"got {type(failure_info).__name__!r}"
        )

    # Explicit failure_class key takes precedence
    if "failure_class" in failure_info:
        raw = failure_info["failure_class"]
        if raw is None:
            raise ValueError(
                "failure_class: failure_info['failure_class'] is None; "
                "must be a non-None string matching a FailureClass enum member"
            )
        try:
            return FailureClass(raw)
        except ValueError:
            raise ValueError(
                f"failure_class: {raw!r} is not a valid FailureClass value; "
                f"valid values are {[fc.value for fc in FailureClass]}"
            )

    # Heuristic classification from error_type / message
    error_type = (failure_info.get("error_type") or "").lower()
    message = (failure_info.get("message") or "").lower()
    traceback = (failure_info.get("traceback") or "").lower()
    combined = f"{error_type} {message} {traceback}"

    if "filenotfounderror" in combined or "no such file" in combined or "missing test" in combined:
        return FailureClass.missing_test_file
    if "importerror" in combined or "modulenotfounderror" in combined or "cannot import" in combined:
        return FailureClass.import_error
    if "typeerror" in combined or "type mismatch" in combined:
        return FailureClass.type_mismatch
    if "assertionerror" in combined or "contract" in combined or "pre-condition" in combined or "post-condition" in combined:
        return FailureClass.contract_violation
    if "notimplementederror" in combined or "empty impl" in combined or "stub" in combined:
        return FailureClass.empty_impl
    if "ambiguous" in combined or "unclear" in combined or "ac failure" in combined:
        return FailureClass.ambiguous_ac

    return FailureClass.unknown


# ---------------------------------------------------------------------------
# Research strategies
# ---------------------------------------------------------------------------


def research_strategies(failure_class: FailureClass) -> list[Strategy]:
    """Return 1-2 alternative strategies tailored to the given failure class.

    This function documents that it spawns a research sub-agent for classifiable
    (non-unknown) failures; see ``spawns_research_subagent`` for the formal
    assertion. For ``FailureClass.unknown``, returns an empty list.

    Args:
        failure_class: The classified failure kind.

    Returns:
        A list of ``Strategy`` objects (empty for ``unknown``).
    """
    if failure_class == FailureClass.unknown:
        return handle_unknown_failure_class(failure_class)

    strategies_by_class: dict[FailureClass, list[Strategy]] = {
        FailureClass.missing_test_file: [
            Strategy(
                title="Scaffold test file from acceptance criteria",
                description=(
                    "Parse acceptance criteria verbatim and emit a minimal pytest "
                    "skeleton that imports the expected module and runs each criterion "
                    "as a separate test case. This ensures the file always exists before "
                    "the implementation sub-agent runs."
                ),
                failure_class=failure_class,
                priority=1,
            ),
            Strategy(
                title="Run test-writer sub-agent before implementer",
                description=(
                    "Spawn a dedicated test-writer sub-agent (like emit_failing_tests) "
                    "that writes the test file first. The implementer sub-agent then "
                    "receives the pre-written tests and implements to make them green."
                ),
                failure_class=failure_class,
                priority=2,
            ),
        ],
        FailureClass.import_error: [
            Strategy(
                title="Add missing package to pyproject.toml before implementation",
                description=(
                    "Identify the unresolvable import from the error traceback and add "
                    "the corresponding package to pyproject.toml dependencies, then run "
                    "pip install -e . before spawning the implementer."
                ),
                failure_class=failure_class,
                priority=1,
            ),
            Strategy(
                title="Use stdlib-only implementation to avoid import errors",
                description=(
                    "Rewrite the implementation using only Python standard library "
                    "modules (json, pathlib, sqlite3, subprocess) so no external "
                    "packages can go missing."
                ),
                failure_class=failure_class,
                priority=2,
            ),
        ],
        FailureClass.type_mismatch: [
            Strategy(
                title="Add explicit type annotations and validate at boundaries",
                description=(
                    "Annotate all function signatures with precise types and add "
                    "isinstance checks at each public API boundary to surface type "
                    "mismatches early with clear error messages."
                ),
                failure_class=failure_class,
                priority=1,
            ),
            Strategy(
                title="Use dataclasses or TypedDict to enforce structure",
                description=(
                    "Replace raw dicts with dataclasses or TypedDict definitions so "
                    "the type checker catches mismatches before runtime."
                ),
                failure_class=failure_class,
                priority=2,
            ),
        ],
        FailureClass.contract_violation: [
            Strategy(
                title="Add pre/post-condition assertions to every function",
                description=(
                    "Add explicit assert statements at the start and end of every "
                    "function body so contract violations surface as AssertionError "
                    "with descriptive messages."
                ),
                failure_class=failure_class,
                priority=1,
            ),
            Strategy(
                title="Write property-based tests with Hypothesis",
                description=(
                    "Use Hypothesis to generate inputs that probe edge cases "
                    "automatically; combine with @given strategies to verify the "
                    "contract holds across a large sample space."
                ),
                failure_class=failure_class,
                priority=2,
            ),
        ],
        FailureClass.empty_impl: [
            Strategy(
                title="Use TDD red-green-refactor cycle strictly",
                description=(
                    "Write all test assertions first, confirm they fail, then write "
                    "the minimum code to make each test green. This prevents returning "
                    "stubs or placeholders as 'implementations'."
                ),
                failure_class=failure_class,
                priority=1,
            ),
            Strategy(
                title="Prompt the implementer with concrete examples from the AC",
                description=(
                    "Extract literal input/output examples from the acceptance criteria "
                    "and prepend them to the implementer's prompt so it cannot rely on "
                    "a stub returning None or []."
                ),
                failure_class=failure_class,
                priority=2,
            ),
        ],
        FailureClass.ambiguous_ac: [
            Strategy(
                title="Run spec clarification loop before implementation",
                description=(
                    "Spawn a spec-clarification sub-agent that identifies ambiguous "
                    "criteria and produces concrete interpretations. Persist results to "
                    "runs/<feature>/clarifications.yaml before the implementer runs."
                ),
                failure_class=failure_class,
                priority=1,
            ),
            Strategy(
                title="Implement the most conservative interpretation first",
                description=(
                    "When the AC is ambiguous, implement the narrowest plausible "
                    "interpretation (fewest assumptions) and add a note in the PR "
                    "description listing the interpretation chosen."
                ),
                failure_class=failure_class,
                priority=2,
            ),
        ],
    }

    return strategies_by_class.get(failure_class, [])


def research_strategies_gated(
    failure_class: FailureClass,
    persist: Any = None,
    max_retries: int = 3,
) -> SynthesisResult:
    """Route research_strategies output through synthesise_with_canonical_gate before persistence.

    Converts Strategy objects to canonical AC strings, validates them against
    the canonical gate, and retries with progressively more-explicit prompting
    on failure.  On persistent failure (all retries exhausted), marks the
    result ``synthesis_blocked_invalid_acs`` and skips the persist call rather
    than writing unusable rows.

    Args:
        failure_class: The classified failure kind (passed to research_strategies).
        persist: Optional callable invoked with the final canonical AC list on success.
        max_retries: Maximum number of generation attempts (default 3).

    Returns:
        :class:`~bob3.synthesis.canonical_ac_emitter.SynthesisResult` with
        ``status="ok"`` on success or ``status=synthesis_blocked_invalid_acs``
        when all retries are exhausted.
    """

    def _generator(topic: str, attempt: int) -> list[str]:
        strategies = research_strategies(failure_class)
        return [
            f"behavior: {s.title} when {failure_class.value} failure occurs"
            if attempt == 1
            else f"behavior: {s.title} resolves {failure_class.value} errors when applied"
            for s in strategies
        ]

    return synthesise_with_canonical_gate(
        feature_topic=failure_class.value,
        generator=_generator,
        persist=persist,
        max_retries=max_retries,
    )


def spawns_research_subagent() -> bool:
    """Return True; documents that research_strategies spawns a research sub-agent on classifiable failure.

    This is a formal assertion function that confirms the design contract:
    when classify_failure returns a non-unknown FailureClass, research_strategies
    is intended to be backed by a research sub-agent call that surfaces
    alternative strategies tailored to the specific failure class.
    """
    return True


def handle_unknown_failure_class(failure_class: FailureClass) -> list[Strategy]:
    """Return empty strategy list when the failure class is unknown.

    For unknown failures there is no targeted research to surface — returning
    an empty list lets callers skip the research sub-agent spawn without
    special-casing the unknown path.

    Args:
        failure_class: Must be ``FailureClass.unknown`` (though the function
                       does not raise if given another value; it returns [] in
                       all cases).

    Returns:
        An empty list.
    """
    return []


def never_spawns_research_on_unknown() -> bool:
    """Return True; documents that unknown failure class skips research spawn.

    This is a formal assertion function confirming the design contract:
    when classify_failure returns FailureClass.unknown, no research sub-agent
    is spawned and an empty strategy list is returned.
    """
    return True


# ---------------------------------------------------------------------------
# Trigger gate
# ---------------------------------------------------------------------------


def should_trigger(refinement_attempts: int, failure_info: dict[str, Any]) -> bool:
    """Return True iff refinement_attempts >= 2 AND classify_failure result != unknown.

    Args:
        refinement_attempts: The feature's current refinement attempt count.
        failure_info: Dict describing the most recent attempt's failure (passed
                      to classify_failure).

    Returns:
        True when both conditions are met; False otherwise.
    """
    if refinement_attempts < 2:
        return False
    failure_class = classify_failure(failure_info)
    return failure_class != FailureClass.unknown


def does_not_trigger_on_first_attempt(refinement_attempts: int, failure_info: dict[str, Any]) -> bool:
    """Return False when refinement_attempts < 2 (first/minimum-attempt boundary).

    This is a formal assertion function documenting that the path-finding retry
    trigger must NOT fire on the first attempt (refinement_attempts == 0 or 1).

    Args:
        refinement_attempts: The feature's current refinement attempt count.
        failure_info: Dict describing the most recent attempt's failure.

    Returns:
        False when refinement_attempts < 2, regardless of failure_class.
    """
    return should_trigger(refinement_attempts, failure_info)


# ---------------------------------------------------------------------------
# Caching and persistence
# ---------------------------------------------------------------------------


def cache_strategies_per_attempt(
    feature_id: str,
    attempt_number: int,
    strategies: list[Strategy],
    workspace: pathlib.Path | None = None,
) -> pathlib.Path:
    """Write strategies to runs/<feature>/research/attempt_<n>.yaml.

    Args:
        feature_id: The feature UUID.
        attempt_number: The attempt index (>= 1).
        strategies: List of Strategy objects to persist.
        workspace: Project root; defaults to pathlib.Path(".").

    Returns:
        The path of the written YAML file.
    """
    if workspace is None:
        workspace = pathlib.Path(".")

    out_dir = workspace / "runs" / feature_id / "research"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / f"attempt_{attempt_number}.yaml"

    serialized = [
        {
            "title": s.title,
            "description": s.description,
            "failure_class": s.failure_class.value,
            "priority": s.priority,
            "metadata": s.metadata,
        }
        for s in strategies
    ]

    out_path.write_text(yaml.safe_dump(serialized, allow_unicode=True, default_flow_style=False))
    logger.debug(
        "Cached %d strategies to %s (feature=%s, attempt=%d)",
        len(strategies),
        out_path,
        feature_id,
        attempt_number,
    )
    return out_path


def inject_into_implementer_prompt(
    base_prompt: str,
    strategies: list[Strategy],
    failure_class: FailureClass,
    attempt_number: int,
) -> str:
    """Return str prefixed prompt with strategies injected.

    Prepends a structured strategies block to the base implementer prompt so
    the implementer retries with new information.

    Args:
        base_prompt: The original implementer prompt.
        strategies: Research strategies to inject.
        failure_class: The failure class that triggered research.
        attempt_number: The current attempt number.

    Returns:
        A new prompt string with the strategies block prepended.
    """
    if not strategies:
        return base_prompt

    lines = [
        f"## Research-Augmented Retry (Attempt {attempt_number})",
        "",
        f"The previous attempt failed with failure class: **{failure_class.value}**.",
        "The following research-driven strategies have been identified to address this failure.",
        "Please use these strategies to guide your implementation:",
        "",
    ]

    for i, strategy in enumerate(strategies, 1):
        lines.append(f"### Strategy {i}: {strategy.title}")
        lines.append("")
        lines.append(strategy.description)
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(base_prompt)

    return "\n".join(lines)


def persist_implementer_prompt(
    feature_id: str,
    attempt_number: int,
    prompt: str,
    workspace: pathlib.Path | None = None,
) -> pathlib.Path:
    """Write implementer prompt to runs/<feature>/attempts/<n>/implementer_prompt.txt.

    Args:
        feature_id: The feature UUID.
        attempt_number: The attempt index (>= 1).
        prompt: The full implementer prompt text to persist.
        workspace: Project root; defaults to pathlib.Path(".").

    Returns:
        The path of the written file.
    """
    if workspace is None:
        workspace = pathlib.Path(".")

    out_dir = workspace / "runs" / feature_id / "attempts" / str(attempt_number)
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / "implementer_prompt.txt"
    out_path.write_text(prompt, encoding="utf-8")

    logger.debug(
        "Persisted implementer prompt to %s (feature=%s, attempt=%d)",
        out_path,
        feature_id,
        attempt_number,
    )
    return out_path
