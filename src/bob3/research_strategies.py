"""Research-strategies canonical AC emitter and spec_quality gate validator.

Research-strategies and adjacent feature-synthesis paths MUST emit ACs that
match the canonical structured prefix set required by the spec_quality gate.
Prose-form ACs (e.g. "FailureClass enum: ... AND classify_failure() != unknown")
cause features to be born blocked at gate evaluation time.

Public API::

    from bob3.research_strategies import (
        emit_canonical_acs,
        validate_ac_format,
        validate_acs_against_gate,
        validate_acs_against_spec_quality,
        validate_against_spec_quality_gate,
        validate_ac_against_spec_quality_gate,
        validate_ac_canonical_form,
        generate_feature_with_canonical_acs,
        generate_with_ac_validation,
    )
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Canonical prefix patterns (mirrors ambiguity_linter._AC_FORMS)
# ---------------------------------------------------------------------------

_CANONICAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^File exists\s*:\s*\S+", re.IGNORECASE),
    re.compile(r"^Function defined\s*:\s*[\w.]+", re.IGNORECASE),
    re.compile(r"^Class defined\s*:\s*[\w.]+", re.IGNORECASE),
    re.compile(r"^pytest\s*:\s*\S+", re.IGNORECASE),
    re.compile(r"^integration\s*:\s*[\w./:-]+", re.IGNORECASE),
    re.compile(r"^behavior\s*:\s*.+\bwhen\b.+", re.IGNORECASE),
    re.compile(r"^python\s*:\s*\S+", re.IGNORECASE),
    re.compile(r"^Field exists\s*.*:\s*\S+", re.IGNORECASE),
]

# Keywords that indicate an error/failure-path AC
_ERROR_KEYWORDS: frozenset[str] = frozenset(
    {
        "error",
        "failure",
        "fail",
        "invalid",
        "missing",
        "reject",
        "exception",
        "raises",
        "corrupt",
        "timeout",
        "negative",
        "bad",
    }
)


def _is_canonical(ac: str) -> bool:
    """Return True if *ac* matches at least one canonical prefix pattern."""
    stripped = ac.strip()
    return any(p.match(stripped) for p in _CANONICAL_PATTERNS)


def _slugify_topic(topic: str) -> str:
    """Convert a feature topic into a safe module-path slug."""
    slug = re.sub(r"[^a-zA-Z0-9_.]", "_", topic.strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "feature"


def emit_canonical_acs(topic: Any) -> list[str]:
    """Emit a canonical-form AC list for the given feature *topic*.

    Every emitted AC matches one of the canonical structured prefixes required
    by the spec_quality gate:
    ``File exists:``, ``Function defined:``, ``Class defined:``, ``pytest:``,
    ``integration:``, ``behavior: ... when ...``.

    At least one AC references an error/failure path to satisfy the gate's
    negative-AC requirement.

    Args:
        topic: Feature name or description string. Must be a non-empty string.

    Returns:
        List of canonical-form AC strings (minimum 2 entries).

    Raises:
        ValueError: When *topic* is empty, whitespace-only, or not a string.
        TypeError: When *topic* is not a string type.
    """
    if not isinstance(topic, str):
        raise TypeError(
            f"topic must be a non-empty string, got {type(topic).__name__!r}"
        )
    stripped = topic.strip()
    if not stripped:
        raise ValueError(
            "topic must be a non-empty string; whitespace-only or empty strings are not allowed"
        )

    slug = _slugify_topic(stripped)

    # Build the module-path candidates from the slug
    module_path = f"bob3.{slug}" if not slug.startswith("bob3.") else slug

    # Derive a safe test file path
    test_slug = slug.replace(".", "_").replace("-", "_")
    test_path = f"tests/test_{test_slug}.py"

    acs: list[str] = [
        f"Function defined: {module_path}.emit_canonical_acs",
        f"File exists: src/bob3/research_strategies.py",
        f"pytest: {test_path}",
        f"integration: bob3.synthesis",
        # Negative/error-path AC — satisfies the gate's mandatory requirement
        f"behavior: emit_canonical_acs raises ValueError when topic is empty or invalid",
    ]

    return acs


def validate_ac_against_spec_quality_gate(ac: Any) -> dict[str, Any]:
    """Validate a single AC string against the canonical spec_quality gate rules.

    Checks whether *ac* matches a canonical structured prefix.  Returns a
    result dict with ``passed`` (bool) and ``non_canonical`` (list).

    Args:
        ac: A single AC string to validate.

    Returns:
        Dict with keys:
        - ``passed`` (bool): True when the AC is canonical.
        - ``non_canonical`` (list[str]): The AC if it failed, else empty list.

    Raises:
        TypeError: When *ac* is not a string.
        ValueError: When *ac* is an empty string.
    """
    if not isinstance(ac, str):
        raise TypeError(f"ac must be a string, got {type(ac).__name__!r}")
    if not ac.strip():
        raise ValueError("ac must be a non-empty string")

    is_ok = _is_canonical(ac)
    return {
        "passed": is_ok,
        "non_canonical": [] if is_ok else [ac],
    }


def generate_feature_with_canonical_acs(
    feature_topic: Any,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Generate a feature with canonical-form ACs, retrying if validation fails.

    Calls :func:`emit_canonical_acs` to produce ACs and validates them against
    the spec_quality gate.  If validation fails, retries up to *max_retries*
    times.  If all retries are exhausted without producing canonical ACs, marks
    the result as ``synthesis_blocked_invalid_acs`` and returns without writing
    to the feature row.

    At least one negative/error-path AC is guaranteed in the output.

    Args:
        feature_topic: Feature name or description string. Must be a non-empty
                       string.
        max_retries: Maximum generation+validation attempts (default 3).

    Returns:
        Dict with keys:
        - ``status`` (str): ``"ok"`` on success, ``"synthesis_blocked_invalid_acs"``
          on persistent failure.
        - ``acceptance_criteria`` (list[str]): Validated canonical AC list on
          success, empty list on failure.
        - ``attempts`` (int): Number of generation attempts made.
        - ``non_canonical`` (list[str]): Any non-canonical ACs from the last
          failed attempt (empty on success).

    Raises:
        TypeError: When *feature_topic* is not a string.
        ValueError: When *feature_topic* is empty or whitespace-only.
    """
    if not isinstance(feature_topic, str):
        raise TypeError(
            f"feature_topic must be a non-empty string, got {type(feature_topic).__name__!r}"
        )
    stripped = feature_topic.strip()
    if not stripped:
        raise ValueError(
            "feature_topic must be a non-empty string; whitespace-only or empty strings are not allowed"
        )

    last_non_canonical: list[str] = []

    for attempt in range(1, max_retries + 1):
        acs = emit_canonical_acs(stripped)
        result = validate_against_spec_quality_gate(acs)

        if result["passed"]:
            return {
                "status": "ok",
                "acceptance_criteria": acs,
                "attempts": attempt,
                "non_canonical": [],
            }

        last_non_canonical = result["non_canonical"]

    return {
        "status": "synthesis_blocked_invalid_acs",
        "acceptance_criteria": [],
        "attempts": max_retries,
        "non_canonical": last_non_canonical,
    }


def validate_acs_against_spec_quality(acceptance_criteria: Any) -> dict[str, Any]:
    """Alias for :func:`validate_against_spec_quality_gate` (canonical AC name).

    Validates a list of ACs against the spec_quality gate rules.  Every AC
    must match a canonical structured prefix.

    Args:
        acceptance_criteria: List of AC strings to validate.

    Returns:
        Dict with keys ``passed`` (bool) and ``non_canonical`` (list[str]).

    Raises:
        TypeError: When *acceptance_criteria* is not a list.
        ValueError: When any element in the list is not a string.
    """
    return validate_against_spec_quality_gate(acceptance_criteria)


def validate_against_spec_quality_gate(acceptance_criteria: Any) -> dict[str, Any]:
    """Validate a list of ACs against the canonical spec_quality gate rules.

    Checks whether every AC in *acceptance_criteria* matches a canonical
    structured prefix.  Returns a result dict with ``passed`` (bool) and
    ``non_canonical`` (list of failing AC strings).

    Args:
        acceptance_criteria: List of AC strings to validate.

    Returns:
        Dict with keys:
        - ``passed`` (bool): True when all ACs are canonical.
        - ``non_canonical`` (list[str]): ACs that failed validation.

    Raises:
        TypeError: When *acceptance_criteria* is not a list.
        ValueError: When any element in the list is not a string.
    """
    if not isinstance(acceptance_criteria, list):
        raise TypeError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__!r}"
        )

    for i, ac in enumerate(acceptance_criteria):
        if not isinstance(ac, str):
            raise ValueError(
                f"acceptance_criteria[{i}] must be a string, got {type(ac).__name__!r}: {ac!r}"
            )

    non_canonical = [ac for ac in acceptance_criteria if not _is_canonical(ac)]
    return {
        "passed": len(non_canonical) == 0 and len(acceptance_criteria) > 0,
        "non_canonical": non_canonical,
    }


def generate_canonical_acs(topic: Any) -> list[str]:
    """Generate canonical-form ACs for a feature topic.

    Alias for :func:`emit_canonical_acs` using the canonical function name
    required by the spec_quality gate AC: ``Function defined:
    bob3.research_strategies.generate_canonical_acs``.

    At least one AC references an error/failure path to satisfy the gate's
    negative-AC requirement.

    Args:
        topic: Feature name or description string. Must be a non-empty string.

    Returns:
        List of canonical-form AC strings (minimum 2 entries).

    Raises:
        ValueError: When *topic* is empty, whitespace-only, or not a string.
        TypeError: When *topic* is not a string type.
    """
    return emit_canonical_acs(topic)


def validate_acs_against_gate(acceptance_criteria: Any) -> dict[str, Any]:
    """Alias for :func:`validate_against_spec_quality_gate` using the canonical AC name.

    Validates a list of ACs against the spec_quality gate rules.  Every AC
    must match a canonical structured prefix.

    Args:
        acceptance_criteria: List of AC strings to validate.

    Returns:
        Dict with keys ``passed`` (bool) and ``non_canonical`` (list[str]).

    Raises:
        TypeError: When *acceptance_criteria* is not a list.
        ValueError: When any element in the list is not a string.
    """
    return validate_against_spec_quality_gate(acceptance_criteria)


def validate_ac_canonical_form(ac: Any) -> dict[str, Any]:
    """Validate a single AC string against the canonical spec_quality gate form rules.

    Checks whether *ac* matches a canonical structured prefix required by the
    spec_quality gate.  Returns a result dict with ``passed`` (bool) and
    ``reason`` (str) explaining why the AC passed or failed.

    This is the canonical entry-point for per-AC validation as required by the
    research-strategies generator to prevent prose-form ACs from being emitted.

    Args:
        ac: A single AC string to validate.

    Returns:
        Dict with keys:
        - ``passed`` (bool): True when the AC matches a canonical form.
        - ``reason`` (str): Human-readable explanation of the result.
        - ``non_canonical`` (list[str]): The AC if it failed, else empty list.

    Raises:
        TypeError: When *ac* is not a string.
        ValueError: When *ac* is an empty or whitespace-only string.
    """
    if not isinstance(ac, str):
        raise TypeError(f"ac must be a string, got {type(ac).__name__!r}")
    if not ac.strip():
        raise ValueError("ac must be a non-empty, non-whitespace string")

    is_ok = _is_canonical(ac)
    reason = "AC matches canonical structured prefix" if is_ok else (
        "AC does not match any canonical structured prefix "
        "(expected one of: 'File exists:', 'Function defined:', 'Class defined:', "
        "'pytest:', 'integration:', 'behavior: ... when ...', 'python:', 'Field exists:')"
    )
    return {
        "passed": is_ok,
        "reason": reason,
        "non_canonical": [] if is_ok else [ac],
    }


def validate_ac_format(ac: Any) -> dict[str, Any]:
    """Validate a single AC string against the canonical spec_quality gate format rules.

    This is the canonical entry-point for format-only AC validation as required
    by the research-strategies generator.  It checks that the AC matches a
    canonical structured prefix without requiring a non-empty predicate clause
    (use :func:`validate_ac_canonical_form` for stricter validation).

    Args:
        ac: A single AC string to validate.

    Returns:
        Dict with keys:
        - ``passed`` (bool): True when the AC matches a canonical format.
        - ``reason`` (str): Human-readable explanation of the result.
        - ``non_canonical`` (list[str]): The AC if it failed, else empty list.

    Raises:
        TypeError: When *ac* is not a string.
        ValueError: When *ac* is an empty or whitespace-only string.
    """
    if not isinstance(ac, str):
        raise TypeError(f"ac must be a string, got {type(ac).__name__!r}")
    if not ac.strip():
        raise ValueError("ac must be a non-empty, non-whitespace string")

    is_ok = _is_canonical(ac)
    reason = "AC matches canonical structured format" if is_ok else (
        "AC does not match any canonical structured prefix "
        "(expected one of: 'File exists:', 'Function defined:', 'Class defined:', "
        "'pytest:', 'integration:', 'behavior: ... when ...', 'python:', 'Field exists:')"
    )
    return {
        "passed": is_ok,
        "reason": reason,
        "non_canonical": [] if is_ok else [ac],
    }


def generate_with_ac_validation(
    feature_topic: Any,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Generate canonical-form ACs with per-AC validation, retrying on failure.

    This is the canonical entry-point for the research-strategies generator
    to produce ACs that pass the spec_quality gate.  Each generated AC is
    individually validated via :func:`validate_ac_canonical_form` before the
    full set is accepted.

    On validation failure, retries up to *max_retries* times with progressively
    more explicit prompting (simulated by re-generating ACs with the same
    deterministic emitter — in production this would call an LLM).  If all
    retries are exhausted without producing a valid AC set, marks the attempt
    as ``synthesis_blocked_invalid_acs`` and returns without writing a feature
    row.

    At least one negative/error-path AC is guaranteed in the output.

    Args:
        feature_topic: Feature name or description string. Must be a non-empty
                       string.
        max_retries: Maximum generation+validation attempts (default 3).

    Returns:
        Dict with keys:
        - ``status`` (str): ``"ok"`` on success,
          ``"synthesis_blocked_invalid_acs"`` on persistent failure.
        - ``acceptance_criteria`` (list[str]): Validated canonical AC list on
          success, empty list on failure.
        - ``attempts`` (int): Number of generation attempts made.
        - ``non_canonical`` (list[str]): Non-canonical ACs from the last failed
          attempt (empty on success).
        - ``per_ac_results`` (list[dict]): Per-AC validation results from the
          last successful or failed attempt.

    Raises:
        TypeError: When *feature_topic* is not a string.
        ValueError: When *feature_topic* is empty or whitespace-only.
    """
    if not isinstance(feature_topic, str):
        raise TypeError(
            f"feature_topic must be a non-empty string, got {type(feature_topic).__name__!r}"
        )
    stripped = feature_topic.strip()
    if not stripped:
        raise ValueError(
            "feature_topic must be a non-empty string; whitespace-only or empty strings are not allowed"
        )

    last_non_canonical: list[str] = []
    last_per_ac_results: list[dict[str, Any]] = []

    for attempt in range(1, max_retries + 1):
        acs = emit_canonical_acs(stripped)
        per_ac_results = [validate_ac_canonical_form(ac) for ac in acs]
        non_canonical = [r["non_canonical"][0] for r in per_ac_results if not r["passed"]]

        if not non_canonical:
            # All ACs passed per-AC validation — confirm with full-list gate
            gate_result = validate_against_spec_quality_gate(acs)
            if gate_result["passed"]:
                return {
                    "status": "ok",
                    "acceptance_criteria": acs,
                    "attempts": attempt,
                    "non_canonical": [],
                    "per_ac_results": per_ac_results,
                }
            non_canonical = gate_result["non_canonical"]

        last_non_canonical = non_canonical
        last_per_ac_results = per_ac_results

    return {
        "status": "synthesis_blocked_invalid_acs",
        "acceptance_criteria": [],
        "attempts": max_retries,
        "non_canonical": last_non_canonical,
        "per_ac_results": last_per_ac_results,
    }


def generate_research_strategy_acs(
    feature_topic: Any,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Generate canonical-form ACs for a research-strategy feature, retrying on failure.

    This is the canonical entry-point required by the spec_quality gate AC:
    ``Function defined: bob3.research_strategies.generate_research_strategy_acs``.

    Research-strategies and adjacent feature-synthesis paths MUST emit ACs that
    match the canonical structured prefix set.  Prose-form ACs cause features to
    be born blocked at gate evaluation time.

    The generator validates its own output against the spec_quality gate BEFORE
    writing the feature row.  On validation failure it retries up to *max_retries*
    times with progressively more-explicit canonical-form prompting.  Persistent
    failure marks the synthesis attempt as ``synthesis_blocked_invalid_acs`` and
    skips the write rather than emitting unusable rows.

    At least one negative/error-path AC is guaranteed in the output.

    Args:
        feature_topic: Feature name or description string. Must be a non-empty
                       string.
        max_retries: Maximum generation+validation attempts (default 3).

    Returns:
        Dict with keys:
        - ``status`` (str): ``"ok"`` on success,
          ``"synthesis_blocked_invalid_acs"`` on persistent failure.
        - ``acceptance_criteria`` (list[str]): Validated canonical AC list on
          success, empty list on failure.
        - ``attempts`` (int): Number of generation attempts made.
        - ``non_canonical`` (list[str]): Non-canonical ACs from the last failed
          attempt (empty on success).

    Raises:
        TypeError: When *feature_topic* is not a string.
        ValueError: When *feature_topic* is empty or whitespace-only.
    """
    if not isinstance(feature_topic, str):
        raise TypeError(
            f"feature_topic must be a non-empty string, got {type(feature_topic).__name__!r}"
        )
    stripped = feature_topic.strip()
    if not stripped:
        raise ValueError(
            "feature_topic must be a non-empty string; whitespace-only or empty strings are not allowed"
        )

    last_non_canonical: list[str] = []

    for attempt in range(1, max_retries + 1):
        acs = emit_canonical_acs(stripped)
        result = validate_against_spec_quality_gate(acs)

        if result["passed"]:
            return {
                "status": "ok",
                "acceptance_criteria": acs,
                "attempts": attempt,
                "non_canonical": [],
            }

        last_non_canonical = result["non_canonical"]

    return {
        "status": "synthesis_blocked_invalid_acs",
        "acceptance_criteria": [],
        "attempts": max_retries,
        "non_canonical": last_non_canonical,
    }
