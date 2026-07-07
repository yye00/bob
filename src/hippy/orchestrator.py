"""hippy.orchestrator — readiness-gate wiring for the bootstrap bypass.

Integrates :func:`hippy.bootstrap_readiness_override.should_bootstrap_bypass`
into the readiness-gating decision so a feature stuck at a low readiness_score
with ``research_iterations == 0`` gets exactly one bypass execute pass.

The gate decision combines two signals:
  1. ``readiness_ok`` — the normal readiness gate verdict (True = would allow).
  2. the bootstrap bypass predicate — True = allow one execute despite a
     failing readiness gate.

When the gate would block but the feature is bypass-eligible, this module
returns an allow decision AND increments ``bootstrap_attempts`` so the bypass
can never fire a second time for the same feature.
"""

from __future__ import annotations

from typing import Any

from hippy.bootstrap_readiness_override import (
    increment_bootstrap_attempts,
    should_bootstrap_bypass,
)


def gate_allows_execution(feature: Any, readiness_ok: bool) -> bool:
    """Return True if *feature* may execute given the readiness gate verdict.

    Args:
        feature: An object exposing ``bootstrap_attempts`` and
            ``research_iterations`` attributes.
        readiness_ok: The normal readiness gate verdict — True when the gate
            would allow execution on its own.

    Returns:
        True if execution should proceed (either the gate passed, or the
        feature is eligible for its one bootstrap bypass); False otherwise.

    Raises:
        TypeError: If *feature* is None or lacks the required attributes.
        ValueError: If either counter is negative or not an int.
    """
    if not isinstance(readiness_ok, bool):
        raise ValueError(
            f"readiness_ok must be a bool, got {type(readiness_ok).__name__!r}"
        )
    if readiness_ok:
        return True
    return should_bootstrap_bypass(feature)


def apply_bootstrap_bypass(feature: Any, readiness_ok: bool) -> bool:
    """Decide whether to execute and consume the bypass if one is used.

    Mutates ``feature.bootstrap_attempts`` (incrementing it) only when the
    readiness gate would have blocked execution and the bypass fires. This
    guarantees the single-bypass invariant: after one bypass execute,
    ``bootstrap_attempts == 1`` and :func:`should_bootstrap_bypass` returns
    False for the same feature.

    Args:
        feature: An object exposing ``bootstrap_attempts`` and
            ``research_iterations`` attributes.
        readiness_ok: The normal readiness gate verdict.

    Returns:
        True if execution should proceed; False otherwise.

    Raises:
        TypeError: If *feature* is None or lacks the required attributes.
        ValueError: If either counter is negative or not an int.
    """
    if readiness_ok:
        return True
    if should_bootstrap_bypass(feature):
        feature.bootstrap_attempts = increment_bootstrap_attempts(
            feature.bootstrap_attempts
        )
        return True
    return False
