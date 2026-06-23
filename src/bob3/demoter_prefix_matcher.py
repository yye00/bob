"""bob3.demoter_prefix_matcher — Prose-AC and integration-AC demoter prefix matching.

Exposes is_structural_prefix_match and get_prose_connectors as the canonical
public surface for START-OF-STRING prefix matching and the prose connector
token registry.

This module ensures that:
- Structural prefix detection requires the prefix to appear at the START of
  the criterion string (after stripping leading whitespace), NOT as a substring.
  A prose AC that quotes "entries with prefix 'pytest:'" mid-sentence does NOT
  match as structural.
- The prose connector registry is the single source of truth for tokens that
  signal descriptive/policy prose in integration-AC bodies. Both the prose-AC
  demoter and the integration-AC resolver MUST consume this registry.
"""
from __future__ import annotations

from bob3.verification.structural_prefix_match import (
    is_structural_prefix_match as _is_structural_prefix_match,
    prose_connector_registry as _prose_connector_registry,
)


def is_structural_prefix_match(criterion: object) -> bool:
    """Return True iff *criterion* starts with a registered structural prefix.

    Leading whitespace is stripped before checking. Non-string input returns
    False. Mid-sentence occurrences of prefix strings (e.g. prose quoting
    'pytest:') return False — only a leading position counts.

    Examples:
      is_structural_prefix_match("pytest: tests/foo.py")              -> True
      is_structural_prefix_match("  file exists: src/bar.py")         -> True
      is_structural_prefix_match("behavior: entries with prefix 'pytest:'") -> False
      is_structural_prefix_match(None)                                 -> False
    """
    return _is_structural_prefix_match(criterion)  # type: ignore[arg-type]


def get_prose_connectors() -> frozenset[str]:
    """Return the canonical frozenset of prose-connector tokens.

    This is the single source of truth for tokens that signal descriptive prose
    or policy language in AC bodies. Both the prose-AC demoter and the
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
    "get_prose_connectors",
]
