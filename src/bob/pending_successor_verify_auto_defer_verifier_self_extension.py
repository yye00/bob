"""Auto-defer verifier-self-extension features to the next generation (F-58426dc0).

At feature-claim time (before the test-writer sub-agent runs), this module
scans the feature's acceptance_criteria for any AC whose body references
verifier internals (``enhanced_verification``, ``verifier``, ``_check_criterion``,
or ``_demote_``) AND whose prefix is ``behavior:``.

If matched, the feature is a verifier-self-extension: the running verifier
cannot validate code that modifies the very mechanism doing the validation
(self-reference treadmill).  The function returns True to signal that the
orchestrator should set status to 'pending_successor_verify' and skip
sub-agent dispatch.  The feature is counted toward ``deferred_count``, not
``failed_count``, in the run summary.

Safe: only behavior-ACs against the verifier itself are deferred.
Structural / integration / file-existence ACs continue down the normal
path.  Non-verifier features are unaffected.  If the heuristic
false-positives, the worst case is that a feature defers one generation
late — no closure regressions.

Public API
----------
pending_successor_verify_auto_defer_verifier_self_extension(
    feature_id, feature_name, acceptance_criteria
)
    Return True when the feature carries a behavior-AC that references
    verifier internals.  Return False otherwise.
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# Prefix regex for behavior: ACs (case-insensitive).
_BEHAVIOR_PREFIX_RE = re.compile(r"^\s*behavior\s*:", re.IGNORECASE)

# Keywords in the AC body that indicate a verifier-self-extension.
# Per feature spec: enhanced_verification, verifier, _check_criterion, _demote_
_VERIFIER_INTERNAL_KEYWORDS: tuple[str, ...] = (
    "enhanced_verification",
    "_check_criterion",
    "_demote_",
    "verifier",
)


def _parse_ac_list(acceptance_criteria) -> list[str] | None:
    """Parse *acceptance_criteria* into a list of strings, or None on failure."""
    if acceptance_criteria is None:
        return []
    if isinstance(acceptance_criteria, list):
        return [str(item) for item in acceptance_criteria]
    if isinstance(acceptance_criteria, str):
        try:
            parsed = json.loads(acceptance_criteria)
            if not isinstance(parsed, list):
                return None
            return [str(item) for item in parsed]
        except (ValueError, TypeError):
            logger.debug(
                "pending_successor_verify_auto_defer: could not parse AC JSON"
            )
            return None
    return None


def _is_behavior_ac_with_verifier_internal(ac: str) -> bool:
    """Return True when *ac* is a behavior: AC that references verifier internals."""
    if not _BEHAVIOR_PREFIX_RE.match(ac):
        return False
    body = _BEHAVIOR_PREFIX_RE.sub("", ac, count=1)
    return any(kw in body for kw in _VERIFIER_INTERNAL_KEYWORDS)


def pending_successor_verify_auto_defer_verifier_self_extension(
    feature_id: str,
    feature_name: str,
    acceptance_criteria,
) -> bool:
    """Return True when the feature should be auto-deferred to the successor generation.

    Scans *acceptance_criteria* for any AC with prefix ``behavior:`` whose body
    references verifier internals (``enhanced_verification``, ``verifier``,
    ``_check_criterion``, or ``_demote_``).  If at least one such AC is found,
    the feature is a verifier-self-extension and must be deferred.

    Args:
        feature_id:           UUID of the feature (used for logging only).
        feature_name:         The feature's name/title (used for logging only).
        acceptance_criteria:  A list of AC strings, a JSON-encoded list, or None.

    Returns:
        True when at least one behavior-AC targets verifier internals.
        False otherwise (including on parse failures or empty AC list).
    """
    ac_list = _parse_ac_list(acceptance_criteria)
    if not ac_list:
        return False

    for ac in ac_list:
        if _is_behavior_ac_with_verifier_internal(ac):
            logger.info(
                "pending_successor_verify_auto_defer: feature %s (%r) has behavior-AC targeting "
                "verifier internals — deferring to successor generation.  AC: %r",
                feature_id,
                feature_name[:80],
                ac[:120],
            )
            return True

    return False


__all__ = [
    "pending_successor_verify_auto_defer_verifier_self_extension",
]
