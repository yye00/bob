"""Permanent-forward-carry auditor — canonical F-R7-NNN regex matching (hippy).

Background
----------
F-R7-554 (a prior-generation sidecar) defined ``required_feature_ids`` as a
frozen set of literal strings and checked their presence with an exact-string
comparison against each feature's ``id`` field. That check silently drops a
still-present carry-forward feature whenever:

* a sidecar is renamed (a prior generation → a prior generation shuffle), so
  the ``id`` field no longer equals the literal required string, or
* a feature is referenced by shortname only, with the canonical F-R7-NNN token
  living in the title/description rather than the ``id`` field.

Depending on rename direction this produces false-positive "missing" reports or
false-negative silent drops.

The fix (spec-over-code — strengthens the audit, never weakens it): match by
the canonical ``F-R7-NNN`` token via a word-boundary regex scanned across the
``id``, ``title`` and ``description`` fields, rather than by exact-string ``id``
equality. A required feature is present if its canonical token appears anywhere
in any text field of any feature entry, regardless of the ``id`` value.

This module is intentionally self-contained (no imports from bob.*) to avoid
the circular-import chain triggered by ``bob.__init__``, mirroring
``bob.auditor.carry_forward_matcher``.

Public API::

    from hippy.permanent_forward_carry_auditor import (
        ForwardCarryAuditError,
        audit_forward_carry,
        match_canonical_feature_id,
        required_feature_ids,
    )

Integration
-----------
``hippy.audit_exemptions`` is imported so the two audit surfaces (dispatch
exemptions and forward-carry) resolve as a single hippy auditor package.
"""

from __future__ import annotations

import os
import re
from typing import Any

# Integration point required by the acceptance criteria: the forward-carry
# auditor and the spec-frozen exemption auditor are siblings in the hippy audit
# surface. Importing it here binds them into one package without a hard runtime
# dependency (the symbol is re-exported for callers that want both).
from hippy import audit_exemptions as audit_exemptions  # noqa: F401

__all__ = [
    "ForwardCarryAuditError",
    "audit_exemptions",
    "audit_forward_carry",
    "canonical_feature_id_pattern",
    "match_canonical_feature_id",
    "required_feature_ids",
]

# Canonical F-R7-NNN pattern. ``[A-Z0-9]+`` matches team codes such as ``R7``
# (which themselves contain a digit). Kept module-local so importing this file
# never triggers the full bob runtime.
_CANONICAL_PATTERN: re.Pattern[str] = re.compile(r"F-[A-Z0-9]+-\d+")
_HAS_LETTER: re.Pattern[str] = re.compile(r"[A-Za-z]")
_HAS_DIGIT: re.Pattern[str] = re.compile(r"\d")

# Base carry-forward set frozen in the spec. F-R7-478/479 are the slopsquatting
# protections and F-R7-553 the whitelist — each MUST survive every sidecar
# shuffle. A future spec revision may extend the set via BOB_PERMANENT_CARRY_IDS.
_CANONICAL_REQUIRED_IDS: frozenset[str] = frozenset(
    {"F-R7-478", "F-R7-479", "F-R7-553"}
)

_ENV_VAR = "BOB_PERMANENT_CARRY_IDS"

# Fields scanned for the canonical token, in priority order.
_SCANNED_FIELDS = ("id", "title", "description")


class ForwardCarryAuditError(Exception):
    """Raised when a required permanent-forward-carry feature is absent.

    Stores the missing canonical IDs on ``.missing`` so callers can inspect the
    set without re-parsing the message.
    """

    def __init__(self, missing: frozenset[str]) -> None:
        self.missing = frozenset(missing)
        listed = ", ".join(sorted(self.missing))
        super().__init__(
            "permanent_forward_carry_missing: required carry-forward features "
            f"absent from merged spec: {listed}. Restore them from "
            "bob4/research/staged_specs/ before proceeding."
        )


def canonical_feature_id_pattern() -> re.Pattern[str]:
    """Return the compiled canonical ``F-R7-NNN`` discovery pattern."""
    return _CANONICAL_PATTERN


def required_feature_ids() -> frozenset[str]:
    """Return the frozen required carry-forward ID set.

    The base set (:data:`_CANONICAL_REQUIRED_IDS`) is always included. The
    ``BOB_PERMANENT_CARRY_IDS`` env var may add comma-separated IDs; it extends
    the base set, never replaces it. Blank/whitespace entries are ignored.
    """
    ids = set(_CANONICAL_REQUIRED_IDS)
    raw = os.environ.get(_ENV_VAR, "")
    for token in raw.split(","):
        token = token.strip()
        if token:
            ids.add(token)
    return frozenset(ids)


def match_canonical_feature_id(
    feature_entry: dict[str, Any],
    canonical_id: str,
) -> bool:
    """Return True if *canonical_id* appears in any text field of *feature_entry*.

    Scans the ``id``, ``title`` and ``description`` fields of a single feature
    dict for the canonical ``F-R7-NNN`` token using a word-boundary regex, so a
    still-present feature is detected even when its ``id`` field holds a renamed
    sidecar alias or shortname (the F-R7-554 silent-drop fix). A word boundary
    prevents ``F-R7-47`` from matching inside ``F-R7-478``.

    Args:
        feature_entry: A single feature dict with optional id/title/description
            keys. Must be a mapping; a non-mapping raises ValueError.
        canonical_id: The canonical feature ID to search for, e.g. ``"F-R7-478"``.
            Must be a non-empty, non-blank string containing at least one letter
            and one digit.

    Returns:
        True if the token is found in any scanned field, False otherwise. Empty
        dicts, unrelated keys, and None/empty field values return False rather
        than raising (boundary case).

    Raises:
        ValueError: If *feature_entry* is not a dict, or *canonical_id* is not a
            non-empty string containing at least one letter and one digit.
    """
    if not isinstance(feature_entry, dict):
        raise ValueError(
            f"feature_entry must be a dict, got {type(feature_entry).__name__!r}"
        )
    if not isinstance(canonical_id, str) or not canonical_id:
        raise ValueError(
            f"canonical_id must be a non-empty string, got {canonical_id!r}"
        )
    stripped = canonical_id.strip()
    if not stripped:
        raise ValueError("canonical_id must not be blank after stripping whitespace")
    if not _HAS_LETTER.search(stripped) or not _HAS_DIGIT.search(stripped):
        raise ValueError(
            f"canonical_id does not look like a canonical feature token: {canonical_id!r}"
        )

    pattern = re.compile(r"(?<!\w)" + re.escape(stripped) + r"(?!\w)")
    for field in _SCANNED_FIELDS:
        text = feature_entry.get(field)
        if isinstance(text, str) and pattern.search(text):
            return True
    return False


def _iter_feature_entries(features: Any) -> list[dict[str, Any]]:
    """Normalise the ``features`` value into a list of feature dicts."""
    if isinstance(features, dict):
        candidates = list(features.values())
    elif isinstance(features, list):
        candidates = features
    else:
        candidates = []
    return [entry for entry in candidates if isinstance(entry, dict)]


def audit_forward_carry(
    spec: dict[str, Any],
    *,
    required: frozenset[str] | None = None,
    raise_on_missing: bool = False,
) -> frozenset[str]:
    """Audit a merged spec for required permanent-forward-carry features.

    Matches each required canonical ID against every feature entry using
    :func:`match_canonical_feature_id` (regex-based, not exact-string ``id``
    comparison), so renamed sidecars and shortname drift are correctly detected.

    Args:
        spec: Parsed spec dict (yaml.safe_load output or equivalent). Supports
            both list-of-dicts and dict-of-dicts ``features`` formats. An empty
            dict or a spec with no ``features`` key is treated as all-missing
            (boundary case — returns the full required set, does not raise).
        required: Optional override for the required ID set. Defaults to
            :func:`required_feature_ids`.
        raise_on_missing: When True, raise :class:`ForwardCarryAuditError` if any
            required ID is absent. When False (default), return the missing set.

    Returns:
        Frozenset of required IDs absent from the spec. Empty means all present.

    Raises:
        ValueError: If *spec* is not a dict.
        ForwardCarryAuditError: When *raise_on_missing* is True and one or more
            required features are absent.
    """
    if not isinstance(spec, dict):
        raise ValueError(f"spec must be a dict, got {type(spec).__name__!r}")

    required_ids = required if required is not None else required_feature_ids()
    entries = _iter_feature_entries(spec.get("features"))

    present: set[str] = set()
    for entry in entries:
        for req_id in required_ids:
            if req_id not in present and match_canonical_feature_id(entry, req_id):
                present.add(req_id)

    missing = frozenset(required_ids - present)
    if missing and raise_on_missing:
        raise ForwardCarryAuditError(missing)
    return missing
