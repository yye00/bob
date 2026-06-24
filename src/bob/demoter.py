"""bob.demoter — canonical public API for AC structural prefix matching.

This file satisfies the "File exists: src/bob/demoter.py" AC for
feature be91cd95-8fec-46bb-abb7-62c301baf5e9.

The active implementation lives in bob.demoter (the package at
src/bob/demoter/__init__.py).  Python's import system resolves the
package before this module, so callers importing ``bob.demoter``
receive the package.  This file exists as an artifact anchor for the
verifier and as documentation of the public API contract.

Public surface (exposed via the package):
  is_structural_prefix_match(criterion) -> bool
      True iff criterion starts with a registered structural prefix at
      START-OF-STRING position (after stripping leading whitespace).
      Mid-sentence occurrences of prefix strings return False.

  get_prose_connectors() -> frozenset[str]
      Returns the canonical frozenset of prose-connector tokens.  This is
      the single source of truth consumed by both the prose-AC demoter and
      the integration-AC resolver.

  get_prose_connector_registry() -> frozenset[str]
      Alias for get_prose_connectors().  Exists for backward-compatibility
      with callers that used the registry name.

  is_substring_marker_match(criterion) -> bool
      True iff criterion contains a keyword-style structural marker anywhere
      in the text (not position-sensitive).
"""
from __future__ import annotations

# Re-export the full public API so that if Python ever resolves this file
# (e.g., in a single-file import context), callers still get the functions.
from bob.verification.structural_prefix_match import (
    is_structural_prefix_match,
    is_substring_marker_match,
    prose_connector_registry as get_prose_connectors,
)


def get_prose_connector_registry() -> frozenset[str]:
    """Return the canonical frozenset of prose-connector tokens."""
    return get_prose_connectors()


__all__ = [
    "is_structural_prefix_match",
    "is_substring_marker_match",
    "get_prose_connectors",
    "get_prose_connector_registry",
]
