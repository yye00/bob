"""Canonical-ID auditor for bob72.

Provides match_by_canonical_id — a regex-based matcher that checks whether
a required F-R7-NNN feature ID appears in any textual field of a spec feature
entry. Fixes the exact-string defect from F-R7-554: when a sidecar is renamed
(bob26 → bob27) or a feature is referenced by shortname only, the old
exact-string check silently drops the carry-forward feature.

Integration with bob3.evaluator is provided via evaluate_canonical_carry so
that the evaluator can verify carry-forward compliance using the same regex
logic rather than exact string comparison.

Implementation delegates to bob3.auditor.carry_forward_matcher which is
self-contained (no bob3.__init__ import chain) to avoid circular imports.
"""

from __future__ import annotations

import os
import re
from typing import Any

from bob3.auditor.carry_forward_matcher import (  # noqa: F401
    match_by_canonical_id,
    resolve_feature_reference,
)

__all__ = [
    "BootstrapAuditError",
    "match_by_canonical_id",
    "evaluate_canonical_carry",
    "extract_canonical_ids",
    "required_feature_ids",
]

# Canonical required IDs — mirrors _CANONICAL_REQUIRED_IDS in the bootstrap auditor.
_CANONICAL_REQUIRED_IDS: frozenset[str] = frozenset({
    "F-R7-478",
    "F-R7-479",
    "F-R7-553",
})

_COMPILED_CANONICAL_PATTERN: re.Pattern[str] = re.compile(r"F-R7-\d+")


class BootstrapAuditError(Exception):
    """Raised when required carry-forward features are absent from the merged spec."""


def required_feature_ids() -> frozenset[str]:
    """Return the frozen set of required permanent carry-forward feature IDs.

    Reads the base set plus any extra IDs from the BOB3_PERMANENT_CARRY_IDS
    environment variable (comma-separated list of F-R7-NNN tokens).

    Returns:
        Frozenset of F-R7-NNN strings that must appear in every merged spec.
    """
    extra_raw = os.environ.get("BOB3_PERMANENT_CARRY_IDS", "")
    extras: set[str] = set()
    for token in extra_raw.split(","):
        token = token.strip()
        if token:
            extras.add(token)
    return _CANONICAL_REQUIRED_IDS | frozenset(extras)


def extract_canonical_ids(spec: dict[str, Any]) -> set[str]:
    """Walk a parsed spec dict and return all F-R7-NNN tokens found.

    Scans each feature's id, title, and description fields for canonical
    ID tokens. This lets the auditor detect a required ID even when the
    feature's 'id' field holds a shortname or sidecar alias.

    Args:
        spec: A parsed spec dict (e.g. from yaml.safe_load).

    Returns:
        Set of F-R7-NNN strings found anywhere in the spec features.
    """
    pattern = _COMPILED_CANONICAL_PATTERN
    found: set[str] = set()
    features = spec.get("features") or []

    def _scan_text(text: Any) -> None:
        if isinstance(text, str):
            found.update(pattern.findall(text))

    if isinstance(features, dict):
        for key, feat in features.items():
            _scan_text(key)
            if isinstance(feat, dict):
                _scan_text(feat.get("id"))
                _scan_text(feat.get("title"))
                _scan_text(feat.get("description"))
    elif isinstance(features, list):
        for feat in features:
            if isinstance(feat, dict):
                _scan_text(feat.get("id"))
                _scan_text(feat.get("title"))
                _scan_text(feat.get("description"))

    return found


def evaluate_canonical_carry(
    spec: dict[str, Any],
    *,
    required: frozenset[str] | None = None,
) -> frozenset[str]:
    """Return the set of required canonical IDs missing from spec.

    Uses regex scanning (via extract_canonical_ids) rather than exact-string
    id lookup so renamed sidecars and shortname aliases are correctly detected.

    Args:
        spec: Parsed spec dict (yaml.safe_load output or equivalent). An empty
            dict or a spec with no 'features' key is treated as all-missing.
        required: Override for the required ID set. Defaults to
            required_feature_ids() (base set + BOB3_PERMANENT_CARRY_IDS env).

    Returns:
        Frozen set of required IDs not found anywhere in the spec. Empty means
        all required features are present.

    Raises:
        ValueError: If spec is not a dict.
    """
    if not isinstance(spec, dict):
        raise ValueError(
            f"spec must be a dict, got {type(spec).__name__!r}"
        )
    if required is None:
        required = required_feature_ids()
    present = extract_canonical_ids(spec)
    return frozenset(required - present)
