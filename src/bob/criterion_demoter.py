"""bob.criterion_demoter — Public demoter API for bob AC classification.

Exposes is_structural_prefix_match and get_prose_connector_registry as the
canonical public surface so callers do not need to import from the
verification sub-package directly.

This module is the public-facing canonical location for the two functions
required by F-0234e7b3. The underlying implementations live in
bob.verification.structural_prefix_match.

Design
------
Structural-prefix matching requires START-OF-STRING position (after stripping
whitespace).  A criterion body that merely *mentions* a prefix token (e.g. a
prose description that quotes "entries with prefix 'pytest:'") must NOT be
classified as structural; it should demote cleanly.

The prose connector registry is the single source of truth for tokens that
signal descriptive/policy prose in integration-AC bodies and integration-prose
demotion.  Both the prose-AC demoter and the integration-AC resolver MUST
consume this registry.
"""
from __future__ import annotations

from bob.enhanced_verification import (
    demote_cross_feature_ac as _demote_cross_feature_ac,
)
from bob.verification.prose_ac_demotion import (
    is_executable_or_structural_criterion as _is_executable_or_structural_criterion,
)
from bob.verification.structural_prefix_match import (
    is_structural_prefix_match as _is_structural_prefix_match,
    prose_connector_registry as _prose_connector_registry,
)

def get_prose_connectors() -> frozenset[str]:
    """Return the canonical frozenset of prose-connector tokens.

    Alias for get_prose_connector_registry(). Single source of truth consumed
    by both the prose-AC demoter and the integration-AC resolver.
    """
    return _prose_connector_registry()


def is_structural_prefix_match(criterion: object) -> bool:
    """Return True iff *criterion* starts with a registered structural prefix.

    Leading whitespace is stripped before checking. Non-string input returns
    False. Mid-sentence occurrences of prefix strings (e.g. prose quoting
    'pytest:') return False — only a leading position counts.

    Examples:
      is_structural_prefix_match("pytest: tests/foo.py")         -> True
      is_structural_prefix_match("  file exists: src/bar.py")    -> True
      is_structural_prefix_match("behavior: ... 'pytest:' ...")   -> False
      is_structural_prefix_match(None)                            -> False
    """
    return _is_structural_prefix_match(criterion)  # type: ignore[arg-type]


def get_prose_connector_registry() -> frozenset[str]:
    """Return the canonical frozenset of prose-connector tokens.

    This is the single source of truth for tokens that signal descriptive prose
    or policy language in AC bodies.  Both the prose-AC demoter and the
    integration-AC resolver MUST consume this registry.

    Covers:
    - Original c09e9e64 form: "all", "every", "route", "through", ";", "no direct"
    - 15d1ac4f regression form: "continues to", "separately", "invariant",
      "whole-suite", "no behavior"
    - Policy phrases: "maintains", "preserves", "ensures", "guarantees",
      "unaffected", "continues", "regression"
    """
    return _prose_connector_registry()


def is_executable_or_structural_criterion(criterion: object) -> bool:
    """Return True when *criterion* is executable or structural.

    Delegates to :func:`bob.verification.prose_ac_demotion.is_executable_or_structural_criterion`.
    Uses START-OF-STRING prefix matching for structural prefixes (so a prose AC
    that merely quotes a prefix like 'pytest:' mid-sentence is NOT mistaken for
    executable) and substring matching for keyword-style markers. Criteria
    beginning with 'behavior:' are definitionally prose and always return False.

    Non-string input returns False (never raises).
    """
    return _is_executable_or_structural_criterion(criterion)  # type: ignore[arg-type]


def prose_connector_registry() -> frozenset[str]:
    """Return the canonical frozenset of prose-connector tokens.

    Single source of truth consumed by both the prose-AC demoter and the
    integration-AC resolver. Alias for :func:`get_prose_connector_registry`.
    Delegates to :func:`bob.verification.structural_prefix_match.prose_connector_registry`.
    """
    return _prose_connector_registry()


def demote_cross_feature_ac(
    criterion: str,
    workspace=None,
) -> "tuple[bool, str] | None":
    """Demote a criterion containing a cross-feature F-RX-YYY reference to PASS.

    Delegates to :func:`bob.enhanced_verification.demote_cross_feature_ac`.
    Returns ``(True, reason)`` when the criterion contains a cross-feature token,
    ``None`` otherwise. Raises ``ValueError`` for invalid (non-string or empty) input.
    """
    return _demote_cross_feature_ac(criterion=criterion, workspace=workspace)
