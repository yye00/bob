"""Public demoter API for bob3 — F-0234e7b3.

Exposes is_structural_prefix_match and get_prose_connector_registry as the
canonical public surface so callers do not need to import from the
verification sub-package directly.

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

from bob3.demoter.structural_prefix_matcher import (
    is_structural_prefix_match,
    is_substring_marker_match,
)
from bob3.demoter.prose_connector_registry import get_prose_connectors


def get_prose_connector_registry() -> frozenset[str]:
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
    return get_prose_connectors()


__all__ = [
    "is_structural_prefix_match",
    "is_substring_marker_match",
    "get_prose_connectors",
    "get_prose_connector_registry",
]
