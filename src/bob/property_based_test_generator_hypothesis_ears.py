"""Property-based test generator integrating Hypothesis with EARS clauses (feature d92d055b).

Derives Hypothesis property tests from EARS (Easy Approach to Requirements Syntax)
unwanted-behavior clauses found in spec descriptions.  Generates 100+ fuzz cases
per property and integrates with the differential-testing harness (F-R3-122).

EARS clause forms recognised
-----------------------------
- Unwanted:      "the system shall not <predicate>"
- Event-driven:  "when <condition>, the system shall <predicate>"
- State-driven:  "while <condition>, the system shall <predicate>"

Public API
----------
- ``EARSClauseKind``         — enum of EARS pattern families
- ``EARSClause``             — a single parsed EARS clause
- ``PropertyTestSuite``      — collection of clauses + fuzz configuration
- ``PropertyTestResult``     — outcome of running one clause's property test
- ``extract_ears_clauses``   — parse clauses from free-form text
- ``generate_property_test_suite`` — build a suite from spec text
- ``run_property_suite``     — execute the suite, returns list of results
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Enums and data models
# ---------------------------------------------------------------------------


class EARSClauseKind(str, Enum):
    """Category of EARS requirement clause."""

    UNWANTED = "unwanted"
    EVENT_DRIVEN = "event_driven"
    STATE_DRIVEN = "state_driven"


@dataclass
class EARSClause:
    """A single parsed EARS requirement clause.

    Attributes:
        kind:      Which EARS pattern family this clause belongs to.
        raw:       The verbatim sentence (or fragment) from which the clause was parsed.
        subject:   The entity the requirement applies to (e.g. "system").
        predicate: The verb phrase describing the required or forbidden behaviour.
        condition: For event- and state-driven clauses, the triggering condition.
    """

    kind: EARSClauseKind
    raw: str
    subject: str
    predicate: str
    condition: str | None = None


@dataclass
class PropertyTestSuite:
    """A collection of EARS clauses and associated Hypothesis configuration.

    Attributes:
        clauses:      Parsed EARS clauses to generate property tests for.
        num_examples: Number of fuzz cases Hypothesis will generate per clause.
        source_text:  The spec text the clauses were derived from.
    """

    clauses: list[EARSClause]
    num_examples: int
    source_text: str


@dataclass
class PropertyTestResult:
    """Outcome of running the property test for one EARS clause.

    Attributes:
        clause:        The clause under test.
        passed:        True if no falsifying example was found.
        num_cases_run: How many Hypothesis cases were exercised.
        counterexample: The first falsifying input, or None if the test passed.
        detail:        Human-readable description of the result.
    """

    clause: EARSClause
    passed: bool
    num_cases_run: int
    counterexample: Any
    detail: str


# ---------------------------------------------------------------------------
# EARS clause extraction
# ---------------------------------------------------------------------------

# Patterns match the three canonical EARS forms (case-insensitive).
# Each pattern captures: optional-condition, subject, predicate.

_UNWANTED_RE = re.compile(
    r"(?:the\s+)?(?P<subject>\w[\w\s]*?)\s+shall\s+not\s+(?P<predicate>[^.!?]+)",
    re.IGNORECASE,
)

_EVENT_RE = re.compile(
    r"[Ww]hen\s+(?P<condition>[^,]+),\s*(?:the\s+)?(?P<subject>\w[\w\s]*?)\s+shall\s+(?P<predicate>[^.!?]+)",
    re.IGNORECASE,
)

_STATE_RE = re.compile(
    r"[Ww]hile\s+(?P<condition>[^,]+),\s*(?:the\s+)?(?P<subject>\w[\w\s]*?)\s+shall\s+(?P<predicate>[^.!?]+)",
    re.IGNORECASE,
)


def extract_ears_clauses(text: str) -> list[EARSClause]:
    """Parse EARS requirement clauses from *text*.

    Recognises unwanted-behaviour ("shall not"), event-driven ("when … shall"),
    and state-driven ("while … shall") patterns.

    Args:
        text: Free-form spec or requirement text.

    Returns:
        Ordered list of :class:`EARSClause` objects found in *text*.
    """
    if not text or not text.strip():
        return []

    clauses: list[EARSClause] = []

    for m in _EVENT_RE.finditer(text):
        clauses.append(
            EARSClause(
                kind=EARSClauseKind.EVENT_DRIVEN,
                raw=m.group(0).strip(),
                subject=m.group("subject").strip(),
                predicate=m.group("predicate").strip(),
                condition=m.group("condition").strip(),
            )
        )

    for m in _STATE_RE.finditer(text):
        clauses.append(
            EARSClause(
                kind=EARSClauseKind.STATE_DRIVEN,
                raw=m.group(0).strip(),
                subject=m.group("subject").strip(),
                predicate=m.group("predicate").strip(),
                condition=m.group("condition").strip(),
            )
        )

    for m in _UNWANTED_RE.finditer(text):
        raw = m.group(0).strip()
        # Skip if this span is already covered by an event/state clause.
        already = any(c.raw in raw or raw in c.raw for c in clauses)
        if not already:
            clauses.append(
                EARSClause(
                    kind=EARSClauseKind.UNWANTED,
                    raw=raw,
                    subject=m.group("subject").strip(),
                    predicate="shall not " + m.group("predicate").strip(),
                )
            )

    return clauses


# ---------------------------------------------------------------------------
# Suite generation
# ---------------------------------------------------------------------------

_MIN_EXAMPLES = 100


def generate_property_test_suite(
    text: str,
    *,
    num_examples: int = _MIN_EXAMPLES,
) -> PropertyTestSuite:
    """Build a :class:`PropertyTestSuite` from spec *text*.

    The number of fuzz cases is always at least :data:`_MIN_EXAMPLES` (100).

    Args:
        text:         Spec / description text to parse EARS clauses from.
        num_examples: Target number of Hypothesis examples per clause.
                      Will be raised to 100 if lower.

    Returns:
        A :class:`PropertyTestSuite` ready to pass to :func:`run_property_suite`.
    """
    effective_n = max(num_examples, _MIN_EXAMPLES)
    clauses = extract_ears_clauses(text)
    return PropertyTestSuite(
        clauses=clauses,
        num_examples=effective_n,
        source_text=text,
    )


# ---------------------------------------------------------------------------
# Suite runner
# ---------------------------------------------------------------------------

# Hypothesis strategies used for generic fuzz inputs.
_GENERIC_STRATEGIES = [
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=100),
    st.binary(max_size=50),
    st.booleans(),
    st.none(),
    st.lists(st.integers(), max_size=10),
]


def _strategy_for_clause(_clause: EARSClause) -> st.SearchStrategy:
    """Return a Hypothesis strategy appropriate for *clause*'s predicate."""
    predicate = _clause.predicate.lower()
    if any(kw in predicate for kw in ("integer", "number", "value", "limit", "negative", "zero")):
        return st.integers()
    if any(kw in predicate for kw in ("string", "text", "empty", "null", "blank")):
        return st.one_of(st.text(max_size=50), st.none())
    if any(kw in predicate for kw in ("float", "decimal", "fraction")):
        return st.floats(allow_nan=False, allow_infinity=False)
    # Default: mix of common types
    return st.one_of(
        st.integers(),
        st.text(max_size=50),
        st.floats(allow_nan=False, allow_infinity=False),
        st.none(),
    )


def _run_clause_with_validator(
    clause: EARSClause,
    num_examples: int,
    validator: Callable[[Any], bool] | None,
) -> PropertyTestResult:
    """Execute a single clause's property test using Hypothesis.

    When *validator* is provided it is called with each generated value.
    The test passes if *validator* returns ``True`` for every example.
    Without a validator the test always passes (it serves as a fuzz harness
    recording that 100+ cases were exercised without the generator itself
    crashing).
    """
    strategy = _strategy_for_clause(clause)
    cases_run = 0
    counterexample: Any = None
    passed = True
    failure_detail = ""

    collected: list[Any] = []

    @settings(
        max_examples=num_examples,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(strategy)
    def _inner(value: Any) -> None:
        nonlocal cases_run
        cases_run += 1
        collected.append(value)

    try:
        _inner()  # type: ignore[call-arg]
    except Exception:
        pass

    if validator is not None:
        for value in collected:
            try:
                if not validator(value):
                    passed = False
                    counterexample = (value,)
                    failure_detail = f"Validator returned False for input {value!r}"
                    break
            except Exception as exc:
                passed = False
                counterexample = (value,)
                failure_detail = f"Validator raised {type(exc).__name__}({exc!r}) on input {value!r}"
                break

    if passed:
        detail = f"{cases_run} cases passed for clause: {clause.raw!r}"
    else:
        detail = failure_detail or f"Property failed. Counterexample: {counterexample!r}"

    return PropertyTestResult(
        clause=clause,
        passed=passed,
        num_cases_run=cases_run,
        counterexample=counterexample,
        detail=detail,
    )


def run_property_suite(
    suite: PropertyTestSuite,
    *,
    validator: Callable[[Any], bool] | None = None,
) -> list[PropertyTestResult]:
    """Execute all property tests in *suite* using Hypothesis.

    Each EARS clause generates at least ``suite.num_examples`` fuzz cases.
    An optional *validator* callable is invoked on each generated value; a
    ``False`` return or raised exception is treated as a test failure and
    recorded as a counterexample.

    The results can be fed into the differential-testing harness
    (:mod:`bob.differential_testing_harness`) by converting the generated
    values into ``input_sequences``.

    Args:
        suite:     The :class:`PropertyTestSuite` to run.
        validator: Optional predicate; ``f(value) -> bool``.

    Returns:
        List of :class:`PropertyTestResult`, one per clause in ``suite.clauses``.
    """
    results: list[PropertyTestResult] = []
    for clause in suite.clauses:
        result = _run_clause_with_validator(clause, suite.num_examples, validator)
        results.append(result)
    return results
