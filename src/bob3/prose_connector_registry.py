"""bob3.prose_connector_registry — Public registry of prose-connector tokens.

Provides two independent partitions of prose-signal tokens:

  prose_connector_registry()
      Returns the frozenset of descriptive-prose connector tokens (the "all",
      "every", "route", etc. set from F-R7-578).  This is the union-compatible
      partner to get_policy_verb_connectors().

  get_policy_verb_connectors()
      Returns the frozenset of policy-verb tokens (MUST/SHOULD/trigger/etc.)
      that signal a runtime-contract body.  Callers MUST union this set with
      the descriptive connectors from prose_connector_registry() when deciding
      whether an integration body should be demoted.

  is_feature_hash_reference(token: str) -> bool
      Returns True for hash-prefix-class identifiers matching the pattern
      r'[0-9a-f]{8}-(class|feature|fn|method)', e.g. 'dd11d1f8-class'.
      The integration-AC handler MUST invoke this predicate on each candidate
      token BEFORE calling _integration_wired — matched tokens are opaque
      feature references and must never be grep'd as Python paths.

Design note: This module is the canonical public entry point.  The underlying
implementation lives in bob3.verification.policy_verb_registry and is re-exported
here so callers can import from a single stable location without knowing the
internal verification package layout.
"""

from __future__ import annotations

import re

from bob3.verification.structural_prefix_match import (
    prose_connector_registry as _descriptive_prose_registry,
)

# ---------------------------------------------------------------------------
# Hash-prefix-class identifier pattern
# Matches tokens like 'dd11d1f8-class', '1c574f4a-feature', 'a3b2c1d0-fn'.
# These are truncated UUIDs referencing other features — NOT Python module paths.
# ---------------------------------------------------------------------------
_FEATURE_HASH_RE = re.compile(r"^[0-9a-f]{8}-(class|feature|fn|method)$")


def prose_connector_registry() -> frozenset[str]:
    """Return the frozenset of descriptive-prose connector tokens.

    These are the 'structural-prose' connectors (F-R7-578) that signal
    descriptive or structural-prose bodies in integration ACs — e.g.:
      "all", "every", "route", "through", ";", "no direct",
      "continues to", "separately", "invariant", "whole-suite",
      "no behavior", "maintains", "preserves", "ensures", "guarantees",
      "unaffected", "continues", "regression"

    This partition is DISTINCT from the policy-verb connectors returned by
    get_policy_verb_connectors().  Callers that decide whether to demote an
    integration body MUST union both partitions.

    Delegates to bob3.verification.structural_prefix_match.prose_connector_registry
    to avoid duplication — that module is the canonical source.
    """
    return _descriptive_prose_registry()


def get_policy_verb_connectors() -> frozenset[str]:
    """Return the frozenset of policy-verb connector tokens.

    These tokens signal runtime-contract prose (MUST/SHOULD/trigger/etc.)
    and are SEPARATE from the descriptive connectors in
    bob3.verification.structural_prefix_match.prose_connector_registry().

    Callers that check for prose bodies MUST union this set with
    prose_connector_registry() from structural_prefix_match so that bodies
    containing only policy verbs are also demoted rather than hard-failing.

    Tokens match as substrings within lowercased body text.
    """
    return frozenset({
        # RFC 2119 modal verbs
        "must",
        "should",
        # Action / event verbs common in AC policy prose
        "trigger",
        "grant",
        "demote",
        "reset",
        "reopen",
        "emit",
        "classify",
        "reclassif",  # prefix covers 'reclassify', 'reclassified', etc.
        "escalate",
        "honor",
        # Partial stems that cover key policy phrases
        "rather than",
        "plausibl",   # covers 'plausible', 'plausibly'
        "fixable",
    })


def get_connectors() -> frozenset[str]:
    """Return the full frozenset of prose-connector tokens (all partitions combined).

    Single-source-of-truth entry point for the complete set of prose-connector
    tokens.  Combines descriptive-prose connectors (prose_connector_registry)
    with policy-verb connectors (get_policy_verb_connectors) so that integration
    AC bodies containing either form are demoted rather than hard-failing.

    Raises:
        None — always returns a frozenset.
    """
    return prose_connector_registry() | get_policy_verb_connectors()


def is_feature_hash_reference(token: str) -> bool:
    """Return True if *token* is a hash-prefix-class identifier.

    Matches the pattern r'[0-9a-f]{8}-(class|feature|fn|method)'.

    These identifiers are truncated UUIDs referencing other features and MUST
    NOT be passed to _integration_wired or grep'd as Python module paths.

    Examples:
      is_feature_hash_reference('dd11d1f8-class')     -> True
      is_feature_hash_reference('1c574f4a-feature')   -> True
      is_feature_hash_reference('a3b2c1d0-fn')        -> True
      is_feature_hash_reference('a3b2c1d0-method')    -> True
      is_feature_hash_reference('bob3.module.func')   -> False
      is_feature_hash_reference('plain-text')         -> False

    Raises:
      ValueError: if token is not a string.
    """
    if not isinstance(token, str):
        raise ValueError(f"token must be a str, got {type(token).__name__!r}")
    return bool(_FEATURE_HASH_RE.match(token))
