"""bob.prose_ac_demoter — Prose-AC and integration-AC demoter (F-R7-578).

Exposes is_structural_prefix_match as the canonical entry point for determining
whether a criterion starts with a registered structural prefix at START-OF-STRING
position (not a substring match).

Root-cause fix for the defect documented in F-R7-578:
  - F-R7-576 used substring matching (`any(marker in cl for marker in markers)`).
    A prose AC quoting "entries with prefix 'pytest:'" mid-sentence was therefore
    classified as structural, causing a false hard-fail.
  - This module delegates to bob.verification.structural_prefix_match which uses
    lstrip().startswith() — only the leading position counts.

The prose connector registry is the single source of truth consumed by both the
prose-AC demoter and the integration-AC resolver.  Callers extend coverage by
adding tokens to bob.prose_connector_registry, not here.

Public API
----------
is_structural_prefix_match(criterion) -> bool
    True iff criterion starts with a registered structural prefix at
    START-OF-STRING position (after stripping leading whitespace).
    Non-string input returns False.

is_prose_ac(criterion) -> bool
    True iff criterion does NOT start with a structural prefix AND does NOT
    contain a keyword-style substring marker.  Used by callers to decide
    whether to demote a failing AC rather than hard-failing the feature.

demote_if_prose(criterion) -> tuple[bool, str] | None
    Returns (True, demotion_reason) if criterion is prose, else None.
    Callers check the return value: None means proceed with normal verification.
"""

from __future__ import annotations

from bob.verification.structural_prefix_match import (
    is_structural_prefix_match,
    is_substring_marker_match,
    prose_connector_registry,
)

__all__ = [
    "is_structural_prefix_match",
    "is_prose_ac",
    "demote_if_prose",
    "prose_connector_registry",
    "get_prose_connectors",
]


def get_prose_connectors() -> frozenset[str]:
    """Return the canonical frozenset of prose-connector tokens.

    Single source of truth consumed by both the prose-AC demoter and the
    integration-AC resolver.  Covers the c09e9e64 original tokens and the
    15d1ac4f regression tokens ("continues to", "separately", "invariant",
    "whole-suite", "no behavior").
    """
    return prose_connector_registry()


def is_prose_ac(criterion: str) -> bool:
    """Return True iff *criterion* is a prose (non-executable) AC.

    A criterion is prose when it:
    - Does NOT start with a registered structural prefix (is_structural_prefix_match
      returns False), AND
    - Does NOT contain a keyword-style substring marker (is_substring_marker_match
      returns False).

    Non-string input returns True (treated as prose / unexecutable).
    """
    if not isinstance(criterion, str):
        return True
    return (
        not is_structural_prefix_match(criterion)
        and not is_substring_marker_match(criterion)
    )


def demote_if_prose(criterion: str) -> tuple[bool, str] | None:
    """Return a passing demotion result if *criterion* is prose, else None.

    Used by the verifier to short-circuit hard-fails on prose ACs.  When the
    verifier cannot statically check a criterion, it should call this function;
    if it returns non-None, the feature is not gate-blocked.

    Returns:
        (True, reason_string) when criterion is prose, so callers treat it as
        a soft-pass.  None when criterion is structural/executable (caller must
        run real verification).
    """
    if is_prose_ac(criterion):
        return (True, "prose AC demoted to warning (F-R7-578)")
    return None
