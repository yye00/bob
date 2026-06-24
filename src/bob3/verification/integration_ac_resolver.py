"""bob3.verification.integration_ac_resolver — Pattern 8 integration AC resolver.

Extracts all dotted-path candidates from an 'integration:' criterion body and
resolves whether any are wired in the workspace.  Prose-policy bodies (those
with spaces and connector tokens) demote to WARNING rather than hard-failing.

Public API
----------
extract_integration_targets(criterion: str) -> list[str]
    Returns every dotted-identifier token (at least two segments) from the body
    after 'integration:'.

resolve_integration_ac(criterion: str, workspace: pathlib.Path) -> tuple[bool, str]
    Returns:
      (True, "")                                    if any extracted target is wired
      (True, "integration AC demoted to warning …") if body is prose-policy
      (False, "no wired integration target found: …") otherwise

log_integration_ac_prose_demoted(criterion, feature_id, scanned_candidates) -> None
    Writes one structured JSON log line per demotion for audit.
"""

from __future__ import annotations

import json
import logging
import pathlib
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bob3.verification.structural_prefix_match import prose_connector_registry
from bob3.verification.policy_verb_registry import (
    is_feature_hash_reference,
    policy_verb_connectors,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger("bob3.verification.integration_demotion")

# Regex: dotted identifiers with at least two segments (e.g. bob3.reviews, bob3.x.y)
_DOTTED_TOKEN_RE = re.compile(r"\b([a-zA-Z_][\w]*(?:\.[a-zA-Z_][\w]*)+)\b")


def extract_integration_targets(criterion: str) -> list[str]:
    """Return every dotted-identifier token from the body after 'integration:'.

    For 'integration: all spec_findings.yaml writes in bob3.reviews route
    through atomic_write_yaml', returns at least ['bob3.reviews'].
    Only tokens with two or more dot-separated segments are included.
    """
    if not isinstance(criterion, str):
        return []
    lower = criterion.lower()
    idx = lower.find("integration:")
    if idx == -1:
        return []
    body = criterion[idx + len("integration:"):]
    return _DOTTED_TOKEN_RE.findall(body)


def _is_prose_body(body: str) -> bool:
    """Return True if *body* looks like human-written policy prose.

    Heuristic: the body contains at least one space AND at least one
    connector token from prose_connector_registry() OR policy_verb_connectors().
    Both partitions are consulted — descriptive-prose connectors (F-R7-578) and
    policy-verb connectors (F-caef0dcf) are separate sets; a body matching
    either is considered policy prose and should be demoted rather than hard-failed.

    Uses word-boundary matching so 'all' in the connectors does not trigger
    on a substring like 'totally', 'locally', etc.
    """
    if " " not in body:
        return False
    body_lower = body.lower()
    all_connectors = prose_connector_registry() | policy_verb_connectors()
    for token in all_connectors:
        pattern = r"\b" + re.escape(token) + r"\b"
        if re.search(pattern, body_lower):
            return True
    return False


def resolve_integration_ac(
    criterion: str, workspace: pathlib.Path
) -> tuple[bool, str]:
    """Resolve an 'integration:' acceptance criterion.

    Returns:
      (True, "")                           — any extracted dotted target is wired
      (True, "integration AC demoted …")   — body looks like prose-policy
      (False, "no wired integration …")    — single/bad dotted target not wired
    """
    from bob3.enhanced_verification import _integration_wired  # avoid circular at module level

    if not isinstance(criterion, str):
        raise TypeError(f"criterion must be a str, got {type(criterion).__name__!r}")

    lower = criterion.lower()
    idx = lower.find("integration:")
    if idx == -1:
        return (False, "no wired integration target found: no 'integration:' marker")

    body = criterion[idx + len("integration:"):]
    targets = extract_integration_targets(criterion)

    for target in targets:
        # Hash-prefix-class identifiers (e.g. 'dd11d1f8-class') are opaque
        # feature references — NEVER grep'd as Python paths.
        if is_feature_hash_reference(target):
            logger.debug("Skipping feature-hash reference %r (not a Python path)", target)
            continue
        try:
            if _integration_wired(workspace, target.rstrip(".")):
                return (True, "")
        except Exception:
            logger.debug("_integration_wired raised for %r", target, exc_info=True)

    if _is_prose_body(body):
        log_integration_ac_prose_demoted(
            criterion=criterion,
            feature_id=None,
            scanned_candidates=targets,
        )
        return (True, "integration AC demoted to warning (F-R7-531 forward-carry)")

    # Single-segment module names (e.g. "spec_linter") are valid Python
    # module identifiers but contain no dots so _DOTTED_TOKEN_RE misses them.
    # Fall back to _integration_wired for any bare snake_case/camelCase
    # identifier in the body that could be a top-level module.
    _single_re = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")
    body_stripped = body.strip()
    for _tok in _single_re.findall(body_stripped):
        if _tok.lower() in ("integration", "the", "and", "or", "of", "in", "is", "a", "an"):
            continue
        try:
            if _integration_wired(workspace, _tok):
                logger.debug(
                    "resolve_integration_ac: single-segment module %r wired via _integration_wired",
                    _tok,
                )
                return (True, "")
        except Exception:
            logger.debug("_integration_wired raised for single-segment %r", _tok, exc_info=True)

    return (False, f"no wired integration target found: {body.strip()}")


def log_integration_ac_prose_demoted(
    criterion: str,
    feature_id: str | None,
    scanned_candidates: list[str],
) -> None:
    """Write one structured JSON log line per prose-demotion for audit.

    Keys: {event, criterion, feature_id, scanned_candidates, timestamp}.
    Logger name: 'bob3.verification.integration_demotion'.
    """
    record = {
        "event": "INTEGRATION_AC_PROSE_DEMOTED",
        "criterion": criterion,
        "feature_id": feature_id,
        "scanned_candidates": scanned_candidates,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    logger.info(json.dumps(record))
