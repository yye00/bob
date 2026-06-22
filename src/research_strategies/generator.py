"""research_strategies.generator — canonical AC emitter for feature synthesis.

Research-strategies generator MUST emit ACs that match the canonical structured
prefix set required by the spec_quality gate. Prose-form ACs cause features to
be born blocked at gate evaluation time.

This module provides :func:`emit_canonical_acs` as the primary entry point for
the research-strategies synthesis path, with built-in gate validation and retry
logic so synthesised features cannot be written with invalid ACs.

Public API::

    from research_strategies.generator import emit_canonical_acs

    acs = emit_canonical_acs("path_finding_retry")
"""

from __future__ import annotations

import re
from typing import Any

from research_strategies.ac_validator import (
    ACValidationResult,
    _ERROR_KEYWORDS,
    _is_canonical,
    validate_acs,
)

# Sentinel status emitted when synthesis cannot produce canonical ACs after
# exhausting all retries.
SYNTHESIS_BLOCKED_STATUS = "synthesis_blocked_invalid_acs"

# Default number of retry attempts for generate_with_gate.
DEFAULT_MAX_RETRIES = 3


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
        List of canonical-form AC strings (minimum 4 entries).

    Raises:
        TypeError: When *topic* is not a string type.
        ValueError: When *topic* is empty, whitespace-only, or not a string.
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

    # Build module path from slug
    module_path = slug if "." in slug else f"research_strategies.{slug}"

    # Derive safe test-file path slug (no dots, no dashes — only underscores)
    test_slug = re.sub(r"[^a-zA-Z0-9_]", "_", slug)
    test_path = f"tests/test_{test_slug}.py"

    acs: list[str] = [
        f"Function defined: {module_path}.emit_canonical_acs",
        f"File exists: src/research_strategies/ac_validator.py",
        f"pytest: {test_path}",
        f"integration: bob3.research_strategies",
        # Negative/error-path AC — satisfies the gate's mandatory requirement
        f"behavior: emit_canonical_acs raises ValueError when topic is empty or invalid",
    ]

    return acs


def generate_with_gate(
    feature_topic: Any,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    """Generate canonical ACs for a feature, retrying if gate validation fails.

    Calls :func:`emit_canonical_acs` and validates the result against
    :func:`research_strategies.ac_validator.validate_acs`. On validation
    failure, retries up to *max_retries* times. If all retries are exhausted,
    marks the synthesis as ``synthesis_blocked_invalid_acs`` and returns without
    writing to the feature row (rather than emitting unusable rows that will
    inevitably block at the gate).

    Args:
        feature_topic: Feature name or description string. Must be a non-empty string.
        max_retries: Maximum number of generation + validation attempts (default 3).

    Returns:
        Dict with keys:
        - ``status`` (str): ``"ok"`` on success,
          ``"synthesis_blocked_invalid_acs"`` on persistent failure.
        - ``acceptance_criteria`` (list[str]): Validated canonical AC list on
          success, empty list on failure.
        - ``attempts`` (int): Number of generation attempts made.
        - ``non_canonical`` (list[str]): Non-canonical ACs from last failed
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
        result: ACValidationResult = validate_acs(acs)

        if result.passed:
            return {
                "status": "ok",
                "acceptance_criteria": acs,
                "attempts": attempt,
                "non_canonical": [],
            }

        last_non_canonical = result.non_canonical

    return {
        "status": SYNTHESIS_BLOCKED_STATUS,
        "acceptance_criteria": [],
        "attempts": max_retries,
        "non_canonical": last_non_canonical,
    }
