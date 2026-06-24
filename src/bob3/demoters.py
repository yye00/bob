"""bob3.demoters — public AC demoter API (F-b3790872).

Exposes is_structural_prefix_match and get_prose_connector_registry as the
canonical public surface so callers do not need to import from sub-packages.

Design
------
Structural-prefix matching requires START-OF-STRING position (after stripping
whitespace). A criterion that merely *mentions* a prefix token mid-sentence
(e.g. a prose description quoting "entries with prefix 'pytest:'") must NOT be
classified as structural; it should demote cleanly.

The prose connector registry is the single source of truth for tokens that
signal descriptive/policy prose in integration-AC bodies and prose-AC demotion.
Both the prose-AC demoter and the integration-AC resolver MUST consume this
registry.

Public API
----------
is_structural_prefix_match(criterion) -> bool
    True iff criterion starts with a registered structural prefix at
    START-OF-STRING position (after stripping leading whitespace).
    Mid-sentence occurrences of prefix strings return False.
    Non-string input returns False.

get_prose_connector_registry() -> frozenset[str]
    Returns the canonical frozenset of prose-connector tokens.
    Single source of truth for both the prose-AC demoter and integration-AC
    resolver.

is_substring_marker_match(criterion) -> bool
    True iff criterion contains a keyword-style structural marker anywhere
    in the text (not position-sensitive). Non-string input returns False.
"""
from __future__ import annotations

from bob3.verification.structural_prefix_match import (
    is_structural_prefix_match,
    is_substring_marker_match,
    prose_connector_registry as _prose_connector_registry,
)


def get_prose_connector_registry() -> frozenset[str]:
    """Return the canonical frozenset of prose-connector tokens.

    This is the single source of truth consumed by both the prose-AC demoter
    and the integration-AC resolver. Callers MUST use this registry rather
    than maintaining their own connector lists.

    Covers:
    - Original c09e9e64 form: "all", "every", "route", "through", ";",
      "no direct"
    - 15d1ac4f regression form: "continues to", "separately", "invariant",
      "whole-suite", "no behavior"
    - Additional policy phrases: "maintains", "preserves", "ensures",
      "guarantees", "unaffected", "continues", "regression"
    """
    return _prose_connector_registry()


__all__ = [
    "is_structural_prefix_match",
    "is_substring_marker_match",
    "get_prose_connector_registry",
]
