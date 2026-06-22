"""bob3.demoter_utils — Shared utilities for prose-AC and integration-AC demoters.

Exposes:
  is_structural_prefix_match(criterion) -> bool
      True iff criterion starts with a registered structural prefix at
      START-OF-STRING position (after stripping leading whitespace).
      Mid-sentence occurrences of prefix strings (e.g. quoting 'pytest:')
      return False.

  get_prose_connector_registry() -> frozenset[str]
      Returns the canonical frozenset of prose-connector tokens.  This is
      the single source of truth consumed by both the prose-AC demoter and
      the integration-AC resolver.

This module is the canonical entry point for F-936068dc — the fix ensuring
demoters match structural prefixes at START-of-string (not as substrings) and
that the prose connector list covers policy phrases such as "continues to",
"separately", "no behavior regression", "invariant", "unaffected", and
"whole-suite".
"""
from __future__ import annotations

from bob3.verification.structural_prefix_match import (
    is_structural_prefix_match,
    prose_connector_registry as _registry,
)


def get_prose_connector_registry() -> frozenset[str]:
    """Return the canonical frozenset of prose-connector tokens.

    Both the prose-AC demoter and the integration-AC resolver MUST consume
    this registry rather than maintaining their own connector lists.

    Covers:
      - Original c09e9e64 form: "all", "every", "route", "through", ";",
        "no direct"
      - 15d1ac4f regression form: "continues to", "separately", "invariant",
        "whole-suite", "no behavior"
      - Policy phrases: "maintains", "preserves", "ensures", "guarantees",
        "unaffected", "continues", "regression"
    """
    return _registry()


__all__ = [
    "is_structural_prefix_match",
    "get_prose_connector_registry",
]
