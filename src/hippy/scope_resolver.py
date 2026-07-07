"""hippy scope resolver — resolve unbounded "comprehensive/full" scope.

Extraction-time gate for the hazard flagged in the hippy/hipsci spec
cross-review: a feature (or spec preamble) that claims unbounded coverage of a
large API surface ("comprehensive", "full", "complete", "everything", "all of",
"100% parity") has no decidable "done". Such a claim MUST be backed by an
explicit IN-SCOPE ENUMERATION (concrete ``Function defined:`` / ``Class
defined:`` / ``File exists:`` ACs, or an ``In-scope:`` line) AND a spec-level
OUT-OF-SCOPE block; otherwise the feature is flagged not-ready for
decomposition/clarification.

This module is the :mod:`hippy` entry point for that check. The detection logic
lives in :mod:`bob.scope_enumeration_linter`; this façade exposes the two
AC-named functions and integrates with :mod:`hippy.spec_extractor`.

Public API::

    from hippy.scope_resolver import (
        resolve_scope_enumeration,
        flag_unbounded_scope,
        ScopeEnumerationResult,
    )
"""

from __future__ import annotations

from typing import Any

from bob.scope_enumeration_linter import (
    ScopeEnumerationResult,
    check_scope_enumeration,
    has_unbounded_scope_word,
)


def resolve_scope_enumeration(
    feature: dict[str, Any],
    *,
    spec: dict[str, Any] | None = None,
) -> ScopeEnumerationResult:
    """Resolve a feature's scope into an explicit in-scope enumeration check.

    Delegates to :func:`bob.scope_enumeration_linter.check_scope_enumeration`.
    Returns a :class:`ScopeEnumerationResult` whose ``is_ready`` is False when an
    unbounded scope word applies to a large surface without both an in-scope
    enumeration and an out-of-scope block.

    Raises
    ------
    TypeError
        If *feature* is not a dict, *spec* is not a dict/None, or
        ``acceptance_criteria`` is not a list.
    """
    return check_scope_enumeration(feature, spec=spec)


def flag_unbounded_scope(
    feature: dict[str, Any],
    *,
    spec: dict[str, Any] | None = None,
) -> list[str]:
    """Return the scope issues for *feature*, empty if the scope is bounded.

    A non-empty list means the feature claims unbounded coverage of a large
    surface without the required in-scope enumeration and/or out-of-scope block
    and MUST be flagged not-ready.

    Raises
    ------
    TypeError
        If *feature* is not a dict, *spec* is not a dict/None, or
        ``acceptance_criteria`` is not a list.
    """
    result = check_scope_enumeration(feature, spec=spec)
    return list(result.issues)


__all__ = [
    "ScopeEnumerationResult",
    "flag_unbounded_scope",
    "has_unbounded_scope_word",
    "resolve_scope_enumeration",
]
