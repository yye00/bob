"""Detect verifier-self-reference in feature acceptance criteria (3c4912e1).

A feature whose behavior: ACs reference verifier internals cannot close in
the generation that owns the running verifier — the verifier cannot validate
behavior it does not yet implement.  ``detect_verifier_self_reference``
identifies these features at claim time so the orchestrator can defer them
to the successor generation via the ``pending_successor_verify`` status.

Public API
----------
detect_verifier_self_reference(acceptance_criteria)
    Return True when any behavior: AC references verifier internals.

VERIFIER_BEHAVIOR_KEYWORDS
    Canonical keywords whose presence in a behavior: AC triggers deferral.
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# Keywords that identify a behavior: AC as targeting verifier internals.
# Any AC whose body (after the 'behavior:' prefix) contains one of these
# triggers deferral to the successor generation.
VERIFIER_BEHAVIOR_KEYWORDS: tuple[str, ...] = (
    "enhanced_verification",
    "verifier",
    "_check_criterion",
    "_demote_",
)

# Matches AC strings that start with the 'behavior:' prefix.
_BEHAVIOR_PREFIX_RE = re.compile(r"^\s*behavior\s*:", re.IGNORECASE)


def detect_verifier_self_reference(
    acceptance_criteria: list[str] | str | None,
) -> bool:
    """Return True when any behavior: AC references verifier internals.

    Scans ``acceptance_criteria`` for any entry whose prefix is ``behavior:``
    and whose body contains at least one of ``VERIFIER_BEHAVIOR_KEYWORDS``.
    When matched, the feature should be deferred to the successor generation
    via ``pending_successor_verify`` status rather than dispatched immediately.

    Args:
        acceptance_criteria: A list of AC strings, a JSON-encoded list of AC
                             strings, or None.  Any other type is treated as
                             an empty list (returns False).

    Returns:
        True when at least one behavior: AC references a verifier-internal
        keyword.  False otherwise (including on any parse error).
    """
    if acceptance_criteria is None:
        return False

    ac_list: list[str]
    if isinstance(acceptance_criteria, str):
        try:
            parsed = json.loads(acceptance_criteria)
            if not isinstance(parsed, list):
                return False
            ac_list = [str(item) for item in parsed]
        except (ValueError, TypeError):
            logger.debug(
                "detect_verifier_self_reference: could not parse AC JSON; returning False"
            )
            return False
    elif isinstance(acceptance_criteria, list):
        ac_list = [str(item) for item in acceptance_criteria]
    else:
        return False

    for ac in ac_list:
        if not _BEHAVIOR_PREFIX_RE.match(ac):
            continue
        # Strip the 'behavior:' prefix to examine the body.
        body = _BEHAVIOR_PREFIX_RE.sub("", ac, count=1).lower()
        if any(kw.lower() in body for kw in VERIFIER_BEHAVIOR_KEYWORDS):
            logger.debug(
                "detect_verifier_self_reference: behavior: AC references verifier internals: %r",
                ac[:120],
            )
            return True

    return False


__all__ = [
    "VERIFIER_BEHAVIOR_KEYWORDS",
    "detect_verifier_self_reference",
]
