"""Prose AC demotion helper — F-R7-576 runtime closure.

When _check_criterion returns False for a criterion that contains NONE of the
recognized structural/executable markers, the failure is a static verifier
limitation, not a code defect. This module provides the demotion logic so that
such criteria pass-with-warning instead of hard-failing the feature.

Public API
----------
is_executable_or_structural_criterion(criterion: str) -> bool
    True when the criterion contains at least one recognized structural marker.

demote_prose_ac(criterion: str) -> tuple[bool, str]
    Returns (True, demotion-reason) for prose criteria to prevent gate-blocking.

log_prose_ac_demoted(criterion: str, feature_id: str | None = None) -> None
    Writes one structured JSON log line per demotion for auditing.

Two-partition connector rule (F-caef0dcf)
-----------------------------------------
Prose-connector tokens are split into two distinct partitions:

  1. Descriptive-prose connectors (bob3.verification.structural_prefix_match
     → prose_connector_registry):
       "all", "every", "route", "through", "continues to", "regression",
       "invariant", "maintains", "preserves", "ensures", "guarantees", etc.
     These signal that a body is describing cross-feature wiring or invariants
     in natural language.

  2. Policy-verb connectors (bob3.verification.policy_verb_registry
     → policy_verb_connectors):
       "must", "should", "trigger", "grant", "demote", "reset", "reopen",
       "emit", "classify", "reclassif", "escalate", "honor", "rather than",
       "plausibl", "fixable".
     These signal runtime-contract language (RFC 2119 modals, action verbs)
     that tests already verify — the static verifier cannot check them and
     must NOT hard-fail on them.

The integration-AC handler (bob3.verification.integration_ac_resolver)
consumes BOTH partitions when deciding whether a body is prose-policy.  This
prevents the failure mode observed in bob3 version 16 round 13 where feature
1c574f4a NH'd because its AC body contained neither a Python-dotted reference
nor any descriptive-prose connector, even though it was unambiguously policy
prose ("MUST trigger fresh-attempt grant rather than NH-demote").

Hash-prefix-class identifiers (e.g. 'dd11d1f8-class') are detected by
is_feature_hash_reference() in policy_verb_registry and must be treated as
opaque feature references — never passed to _integration_wired.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from bob3.verification.structural_prefix_match import (
    is_structural_prefix_match,
    is_substring_marker_match,
)

logger = logging.getLogger("bob3.verification.prose_demotion")


def is_executable_or_structural_criterion(criterion: str) -> bool:
    """Return True when *criterion* is executable or structural.

    Uses prefix-position matching for structural prefixes (so mid-sentence
    quotes of a prefix like 'pytest:' are never mistaken for executable
    criteria) and substring matching for keyword-style markers.

    Criteria that begin with 'behavior:' are definitionally prose descriptions
    and are never executable, even when their body happens to quote a keyword
    marker phrase (e.g. "behavior: foo returns 'no errors'").
    """
    if not isinstance(criterion, str):
        return False
    if criterion.lstrip().lower().startswith("behavior:"):
        return False
    return is_structural_prefix_match(criterion) or is_substring_marker_match(criterion)


def demote_prose_ac(criterion: str) -> tuple[bool, str]:
    """Return a passing result with a demotion reason for prose criteria.

    Called when _check_criterion returned False AND
    is_executable_or_structural_criterion returned False — meaning the verifier
    has no way to check the criterion statically, and blocking the feature on it
    would cause indefinite respinning (the b6873bac pattern).
    """
    return (True, "prose AC demoted to warning (F-R7-531 forward-carry)")


def log_prose_ac_demoted(criterion: str, feature_id: str | None = None) -> None:
    """Write one structured JSON log line for a demoted prose AC.

    Keys: {event, criterion, feature_id, timestamp}. The logger is named
    'bob3.verification.prose_demotion' so callers can route or suppress it
    independently from the main verification logger.
    """
    record = {
        "event": "PROSE_AC_DEMOTED",
        "criterion": criterion,
        "feature_id": feature_id,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    logger.info(json.dumps(record))
