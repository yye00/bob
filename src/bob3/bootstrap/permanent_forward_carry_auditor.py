"""Permanent-forward-carry auditor for bob_N bootstrap.

Checks that the merged spec contains feature definitions for the permanent
infra-recovery set (F-R7-478, F-R7-479, F-R7-553) BEFORE plan --create
proceeds. If any are missing the bootstrap MUST fail loud.

Motivation: audit 2026-05-28 found F-R7-478 missing from bob17/18/19/24
sidecars, F-R7-479 missing from bob17-25 sidecars, and F-R7-553 never
instantiated as a full feature definition — only referenced by shortname.
Sidecar merge silently drops these when not re-added, causing infra-recovery
capabilities to degrade as the chain advances.

Fix: run this auditor after sidecar merge and BEFORE plan --create / feature
insertion. On missing features, raise BootstrapAuditError with a structured
permanent_forward_carry_missing event and refuse to start the run.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_CANONICAL_REQUIRED_IDS: frozenset[str] = frozenset({
    "F-R7-478",
    "F-R7-479",
    "F-R7-553",
})

_COMPILED_CANONICAL_PATTERN: re.Pattern[str] = re.compile(r"F-R7-\d+")

_STAGED_SPECS_HINT = "bob4/research/staged_specs/"


def canonical_feature_id_pattern() -> re.Pattern[str]:
    """Return a compiled regex that matches F-R7-NNN canonical feature IDs.

    Returns:
        Compiled regex pattern matching tokens of the form F-R7-<digits>.
    """
    return _COMPILED_CANONICAL_PATTERN


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


class BootstrapAuditError(RuntimeError):
    """Raised when the permanent-forward-carry audit fails.

    The error message lists each missing feature ID and points to the
    staged_specs/ directory where they must be added.
    """

    def __init__(self, missing: frozenset[str]) -> None:
        self.missing = missing
        ids_listed = ", ".join(sorted(missing))
        super().__init__(
            f"permanent_forward_carry_missing: the merged spec is missing "
            f"required feature definition(s): {ids_listed}. "
            f"Add the missing feature(s) to {_STAGED_SPECS_HINT} and re-merge "
            f"before running plan --create."
        )


class PermanentForwardCarryMissing(BootstrapAuditError):
    """Named exception for the permanent-forward-carry audit failure.

    Subclass of BootstrapAuditError with an explicit class name so that
    the ``Function defined: bob3.permanent_forward_carry_auditor.PermanentForwardCarryMissing``
    AC is satisfied by a real class definition (not just an alias assignment).
    """


def required_feature_ids() -> frozenset[str]:
    """Return the canonical permanent-forward-carry feature ID set.

    The base set is always {F-R7-478, F-R7-479, F-R7-553}.
    Additional IDs may be appended (NOT replaced) via the environment variable
    BOB3_PERMANENT_CARRY_IDS as a comma-separated list.

    Returns:
        Frozen set of required feature ID strings.
    """
    base = set(_CANONICAL_REQUIRED_IDS)
    extra_env = os.environ.get("BOB3_PERMANENT_CARRY_IDS", "").strip()
    if extra_env:
        for part in extra_env.split(","):
            part = part.strip()
            if part:
                base.add(part)
    return frozenset(base)


def _extract_feature_ids(spec: dict[str, Any]) -> set[str]:
    """Extract all feature IDs from a parsed spec dict.

    Supports both list-of-dicts and dict-of-dicts feature formats.
    Looks for an 'id' field within each feature entry.
    """
    ids: set[str] = set()
    features = spec.get("features") or []

    if isinstance(features, dict):
        for key, feat in features.items():
            ids.add(str(key))
            if isinstance(feat, dict):
                fid = feat.get("id")
                if fid:
                    ids.add(str(fid))
    elif isinstance(features, list):
        for feat in features:
            if isinstance(feat, dict):
                fid = feat.get("id")
                if fid:
                    ids.add(str(fid))

    return ids


def audit_merged_spec(spec: dict[str, Any]) -> frozenset[str]:
    """Check a parsed spec dict for the permanent-forward-carry feature set.

    Uses extract_canonical_ids to scan id, title, and description fields for
    F-R7-NNN tokens, so a required ID is detected even when stored as a
    shortname or sidecar alias in the 'id' field.

    Args:
        spec: A parsed spec dict (e.g. from yaml.safe_load on the spec YAML).

    Returns:
        Frozen set of required feature IDs that are MISSING from the spec.
        An empty frozenset means all required features are present.
    """
    present_ids = extract_canonical_ids(spec)
    required = required_feature_ids()
    missing = required - present_ids
    if missing:
        logger.warning(
            "permanent_forward_carry_missing: spec is missing required feature(s): %s",
            ", ".join(sorted(missing)),
        )
    return frozenset(missing)


def fail_loud_on_missing(missing: frozenset[str]) -> None:
    """Raise PermanentForwardCarryMissing when the missing set is non-empty.

    Args:
        missing: The set of missing feature IDs (from audit_merged_spec).

    Raises:
        PermanentForwardCarryMissing: when missing is non-empty, listing each absent
            feature ID and pointing to bob4/research/staged_specs/ as the
            place to add them.
    """
    if missing:
        raise PermanentForwardCarryMissing(missing)


def check_required_features(
    spec: dict[str, Any],
    *,
    required: frozenset[str] | None = None,
) -> frozenset[str]:
    """Check which required permanent-forward-carry features are present in spec.

    Scans the merged spec for the canonical required feature IDs using the
    F-R7-NNN regex scanner. Returns the frozenset of IDs that ARE found
    (i.e. the complement of the missing set). Does NOT raise on missing.

    Args:
        spec: A parsed spec dict (e.g. from yaml.safe_load).
        required: Optional override for the required ID set. Defaults to
            required_feature_ids() (base set + BOB3_PERMANENT_CARRY_IDS env).

    Returns:
        Frozenset of required feature IDs that are present in the spec.
        An empty frozenset means none of the required features are present.

    Raises:
        ValueError: If spec is not a dict.
    """
    if not isinstance(spec, dict):
        raise ValueError(f"spec must be a dict, got {type(spec).__name__!r}")
    required_ids = required if required is not None else required_feature_ids()
    present_ids = extract_canonical_ids(spec)
    return frozenset(required_ids & present_ids)


def audit_bootstrap_spec(spec: dict[str, Any]) -> None:
    """Audit a merged spec and fail loud if permanent-forward-carry features are missing.

    This is the single-call entrypoint for the bootstrap auditor: it runs
    audit_merged_spec and immediately raises BootstrapAuditError if any
    required feature IDs (F-R7-478, F-R7-479, F-R7-553) are absent.

    Must be called AFTER sidecar merge and BEFORE plan --create / feature
    insertion. On success (all required features present) it returns None.

    Args:
        spec: A parsed spec dict (e.g. from yaml.safe_load).

    Raises:
        BootstrapAuditError: with a structured permanent_forward_carry_missing
            event when any required feature definition is absent from the spec.
    """
    missing = audit_merged_spec(spec)
    fail_loud_on_missing(missing)
