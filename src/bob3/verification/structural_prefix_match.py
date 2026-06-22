"""Structural prefix matching — F-30176f30 / F-R7-576 + F-R7-577 fix.

Provides the canonical classification for 'is this AC structural/executable?'
by splitting the old monolithic marker list into two distinct strategies:

  is_structural_prefix_match(criterion)
      True iff the criterion STARTS WITH a registered structural prefix after
      stripping leading whitespace.  Prefix position is required — mid-sentence
      quotes of a prefix (e.g. "entries with prefix 'pytest:'") never match.

  is_substring_marker_match(criterion)
      True iff the criterion CONTAINS a keyword-style marker anywhere in the
      text.  Used only for markers that legitimately appear mid-sentence
      ("function implemented", "no compilation errors", etc.).

  prose_connector_registry()
      Returns the frozenset of connector tokens used by both the prose-AC
      demoter (F-R7-576) and the integration-AC resolver (F-R7-577).  Callers
      MUST consume this registry rather than maintaining their own copies.

Design note: keeping the registry as a frozenset returned by a function (rather
than a module-level name) makes it easy to extend from tests or callers via
monkeypatching without touching gating logic.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Structural prefix set
# These markers are only significant when they appear at the START of the
# criterion (after stripping whitespace).  A mid-sentence occurrence (e.g.
# inside quotes or in prose) must NOT trigger structural classification.
# ---------------------------------------------------------------------------
_STRUCTURAL_PREFIXES: tuple[str, ...] = (
    "pytest:",
    "python:",
    "ci tests:",
    "forbidden_imports:",
    "behavioral_signature:",
    "deterministic_output:",
    "resource_limit:",
    "test_coupling:",
    "mms:",
    "conserves:",
    "file exists:",
    "file exist:",
    "function defined:",
    "class defined:",
    "integration:",
)

# ---------------------------------------------------------------------------
# Substring marker set
# These keywords may legitimately appear anywhere in the criterion text and
# still indicate an executable/structural criterion.
# ---------------------------------------------------------------------------
_SUBSTRING_MARKERS: tuple[str, ...] = (
    "function implemented",
    "method implemented",
    "cmake",
    "no compilation errors",
    "no errors",
)


def is_structural_prefix_match(criterion: str) -> bool:
    """Return True iff *criterion* starts with a registered structural prefix.

    Leading whitespace is stripped before checking.  Mid-sentence occurrences
    of prefix strings (e.g. a prose criterion that quotes 'pytest:') return
    False because the prefix is not at position 0.
    """
    if not isinstance(criterion, str):
        return False
    stripped = criterion.lstrip().lower()
    return any(stripped.startswith(prefix) for prefix in _STRUCTURAL_PREFIXES)


def is_substring_marker_match(criterion: str) -> bool:
    """Return True iff *criterion* contains a keyword-style structural marker.

    These markers ('function implemented', 'cmake', etc.) are valid anywhere
    in the criterion text — they do not require a leading position.
    """
    if not isinstance(criterion, str):
        return False
    lower = criterion.lower()
    return any(marker in lower for marker in _SUBSTRING_MARKERS)


def prose_connector_registry() -> frozenset[str]:
    """Return the canonical frozenset of prose-connector tokens.

    Both the prose-AC demoter (bob3.verification.prose_ac_demotion) and the
    integration-AC resolver (bob3.verification.integration_ac_resolver) MUST
    consume this registry rather than defining their own connector lists.
    Extending coverage requires a change here only.

    Covers:
      - Original c09e9e64 form: "all", "every", "route", "through", ";",
        "no direct"
      - 15d1ac4f regression form: "continues to", "separately", "invariant",
        "whole-suite", "no behavior"
      - Additional policy phrases: "maintains", "preserves", "ensures",
        "guarantees", "unaffected", "continues", "regression"
    """
    return frozenset({
        # c09e9e64 originals (and the multi-target 'and'/'or'/'via'/'routes' tokens)
        "all",
        "every",
        "route",
        "routes",
        "through",
        ";",
        "no direct",
        "via",
        "and",
        "or",
        # 15d1ac4f regression tokens
        "continues to",
        "separately",
        "continues",
        "regression",
        "whole-suite",
        "no behavior",
        # Additional policy-prose coverage
        "maintains",
        "preserves",
        "ensures",
        "guarantees",
        "invariant",
        "unaffected",
    })
