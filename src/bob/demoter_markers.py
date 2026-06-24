"""bob.demoter_markers — Canonical marker registry for prose-AC and integration-AC demoters.

Exposes:
  is_structural_prefix_match(criterion) -> bool
      True iff criterion starts with a registered structural prefix at
      START-OF-STRING position (after stripping leading whitespace).
      Mid-sentence occurrences (e.g. prose quoting 'pytest:') return False.

  get_connector_registry() -> frozenset[str]
      Returns the canonical frozenset of prose-connector tokens used by
      both the prose-AC demoter and the integration-AC resolver.
      Single source of truth — callers MUST NOT maintain their own copies.

Root-cause context (F-R7-576 + F-R7-577):
  F-R7-576 used substring matching so a prose AC containing "pytest:"
  mid-sentence was classified as structural, causing false hard-fails.
  This module delegates to bob.verification.structural_prefix_match
  which uses lstrip().startswith() — only leading position counts.

  F-R7-577's connector list was too narrow; phrases like "continues to",
  "separately", "invariant", "whole-suite", "no behavior" were not
  recognised as prose connectors.  get_connector_registry() covers all
  of them.
"""
from __future__ import annotations

from bob.verification.structural_prefix_match import (
    is_structural_prefix_match as _is_structural_prefix_match,
    prose_connector_registry as _prose_connector_registry,
)


def is_structural_prefix_match(criterion: object) -> bool:
    """Return True iff *criterion* starts with a registered structural prefix.

    Leading whitespace is stripped before checking.  Non-string input returns
    False.  Mid-sentence occurrences of prefix strings (e.g. prose quoting
    'entries with prefix "pytest:"') return False — only a leading position
    counts.

    Examples::

        is_structural_prefix_match("pytest: tests/foo.py")              -> True
        is_structural_prefix_match("  file exists: src/bar.py")         -> True
        is_structural_prefix_match("behavior: entries with prefix 'pytest:'") -> False
        is_structural_prefix_match(None)                                 -> False
    """
    return _is_structural_prefix_match(criterion)  # type: ignore[arg-type]


def get_connector_registry() -> frozenset[str]:
    """Return the canonical frozenset of prose-connector tokens.

    This is the single source of truth for tokens that signal descriptive prose
    or policy language in AC bodies.  Both the prose-AC demoter and the
    integration-AC resolver MUST consume this registry rather than maintaining
    their own copies.

    Covers:
    - Original c09e9e64 form: "all", "every", "route", "through", ";", "no direct"
    - 15d1ac4f regression form: "continues to", "separately", "invariant",
      "whole-suite", "no behavior"
    - Policy phrases: "maintains", "preserves", "ensures", "guarantees",
      "unaffected", "continues", "regression"
    """
    return _prose_connector_registry()


__all__ = [
    "is_structural_prefix_match",
    "get_connector_registry",
]
