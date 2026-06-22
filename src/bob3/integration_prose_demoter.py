"""bob3.integration_prose_demoter — Integration-AC prose demoter (F-R7-577 / 1a58a41c).

Exposes is_executable_or_structural_criterion as the canonical entry point for
determining whether an integration-AC criterion is executable/structural (and
must not be demoted) versus prose (and should demote to WARNING rather than
hard-failing the feature).

Root-cause fix for the defect documented in F-R7-577:
  - The original integration-prose connector heuristic only recognized
    {"all", "every", "route", "through", ";", "no direct"}.
  - The 15d1ac4f form "regression-sweep ... continues to run whole-suite pytest
    separately" used "continues to", "separately", "invariant", "whole-suite",
    "no behavior" — none of which were in the original list — causing a false
    hard-fail.

Design
------
The prose connector registry (bob3.prose_connector_registry.get_connectors) is
the single source of truth for tokens that signal descriptive/policy prose.
This module consumes that registry — it never defines its own token lists.

Public API
----------
is_executable_or_structural_criterion(criterion) -> bool
    True iff criterion is a real executable/structural AC (not prose).
    Delegates to bob3.verification.structural_prefix_match for prefix matching.

is_integration_prose_body(body) -> bool
    True iff the body after 'integration:' looks like human-written prose.
    Exposes the internal heuristic from bob3.verification.integration_ac_resolver.
"""

from __future__ import annotations

from bob3.verification.structural_prefix_match import (
    is_structural_prefix_match,
    is_substring_marker_match,
)
from bob3.verification.integration_ac_resolver import _is_prose_body

__all__ = [
    "is_executable_or_structural_criterion",
    "is_integration_prose_body",
]


def is_executable_or_structural_criterion(criterion: str) -> bool:
    """Return True iff *criterion* is an executable or structural AC.

    An AC is executable/structural when it:
    - Starts with a registered structural prefix at START-OF-STRING position
      (is_structural_prefix_match returns True), OR
    - Contains a keyword-style substring marker (is_substring_marker_match
      returns True, for markers like "function implemented", "no compilation
      errors").

    Non-string input returns False (treated as non-structural / unexecutable).
    Mid-sentence occurrences of prefix strings (e.g. a prose criterion that
    quotes "entries with prefix 'pytest:'") return False because the prefix
    is not at START-OF-STRING position.

    This is the canonical entry point for the integration-AC resolver to
    decide whether an AC body should be demoted (when False) or hard-verified
    (when True).
    """
    if not isinstance(criterion, str):
        return False
    return is_structural_prefix_match(criterion) or is_substring_marker_match(criterion)


def is_integration_prose_body(body: str) -> bool:
    """Return True iff *body* (after 'integration:') looks like policy prose.

    Delegates to bob3.verification.integration_ac_resolver._is_prose_body,
    which checks for at least one space AND at least one connector token from
    the prose connector registry (all partitions combined).

    Non-string input returns False.
    """
    if not isinstance(body, str):
        return False
    return _is_prose_body(body)
