"""bob3.demoter_gates — Public gate API for prose-AC and integration-AC demotion.

Exposes is_structural_prefix_match and get_prose_connectors as the canonical
public surface so callers do not need to import from sub-packages directly.

This module satisfies F-0a9d5eb0: the demoter modules from F-R7-576 and
F-R7-577 MUST expose is_structural_prefix_match (prefix-position check, not
substring) AND a documented connector-token registry via get_prose_connectors.

Design
------
Structural-prefix matching requires START-OF-STRING position (after stripping
whitespace). A criterion body that merely *mentions* a prefix token mid-sentence
(e.g. "entries with prefix 'pytest:'") must NOT be classified as structural;
it should demote cleanly.

The prose connector registry is the single source of truth for tokens that
signal descriptive/policy prose in integration-AC bodies. Both the prose-AC
demoter and the integration-AC resolver MUST consume this registry rather than
maintaining their own connector lists.

Also re-exports startup-crash exemption helpers (F-R7-613) so orchestrator
callers can import both demoter gates and crash-exemption from a single module.
"""
from __future__ import annotations

from bob3.demoter.structural_prefix_matcher import (
    is_structural_prefix_match,
    is_substring_marker_match,
)
from bob3.demoter.prose_connector_registry import get_prose_connectors
from bob3.startup_crash_exempt import (
    is_transport_crash,
    should_exempt_from_retry,
)


__all__ = [
    "is_structural_prefix_match",
    "is_substring_marker_match",
    "get_prose_connectors",
    "is_transport_crash",
    "should_exempt_from_retry",
]
