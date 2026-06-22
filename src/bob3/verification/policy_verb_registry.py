"""Policy-verb connector registry — F-caef0dcf / F-R7-577 + F-R7-578 extension.

Provides a second partition of prose-signal tokens specifically for
*runtime-contract* (policy) language:

  policy_verb_connectors()
      Returns the frozenset of policy-verb tokens that signal a runtime
      contract body.  These are DISTINCT from the descriptive-prose connectors
      returned by prose_connector_registry() in structural_prefix_match.py.
      Callers MUST union both sets when deciding whether an integration body
      should be demoted rather than hard-failing.

  is_feature_hash_reference(token: str) -> bool
      Returns True for tokens that match the hash-prefix-class identifier
      pattern ``r'[0-9a-f]{8}-(class|feature|fn|method)'``, e.g.:
        - 'dd11d1f8-class'
        - '1c574f4a-feature'
        - 'a3b2c1d0-fn'
      Returns False for dotted Python paths ('bob3.module.func') and
      plain-text phrases.

      The integration-AC handler MUST invoke this predicate on each candidate
      token BEFORE calling _integration_wired.  Matched hash-references are
      opaque feature references — they must never be grep'd as Python paths.

Design note: keeping each registry as a function returning frozenset lets
callers extend or monkeypatch in tests without touching gate logic.  The
two-partition rule (descriptive vs policy) is documented in
bob3.verification.prose_ac_demotion for discoverability.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Hash-prefix-class identifier pattern
# Matches tokens like 'dd11d1f8-class', '1c574f4a-feature', 'a3b2c1d0-fn'.
# These are truncated UUIDs referencing other features — NOT Python module paths.
# ---------------------------------------------------------------------------
_FEATURE_HASH_RE = re.compile(r"^[0-9a-f]{8}-(class|feature|fn|method)$")


def policy_verb_connectors() -> frozenset[str]:
    """Return the frozenset of policy-verb connector tokens.

    These tokens signal runtime-contract prose (MUST/SHOULD/trigger/etc.)
    and are SEPARATE from the descriptive connectors in prose_connector_registry().

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


def is_feature_hash_reference(token: str) -> bool:
    """Return True if *token* is a hash-prefix-class identifier.

    Matches the pattern r'[0-9a-f]{8}-(class|feature|fn|method)'.

    Examples:
      is_feature_hash_reference('dd11d1f8-class')     -> True
      is_feature_hash_reference('1c574f4a-feature')   -> True
      is_feature_hash_reference('a3b2c1d0-fn')        -> True
      is_feature_hash_reference('bob3.module.func')   -> False
      is_feature_hash_reference('plain-text')         -> False
    """
    if not isinstance(token, str):
        return False
    return bool(_FEATURE_HASH_RE.match(token))
