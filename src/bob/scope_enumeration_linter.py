"""Scope-enumeration linter — resolve unbounded scope into an explicit surface.

bob's per-AC ambiguity linter targets vague *acceptance criteria*. This module
targets a different hazard: a vague *feature/project SCOPE* statement. When a
feature (or the spec preamble) claims unbounded coverage of a large API surface
with a word like "comprehensive", "full", "complete", "everything", "all of",
or "100% parity", an autonomous builder has no decidable "done": it either
over-reaches (chasing an unbounded tail, never converging) or declares victory
on a subset masquerading as the whole.

Fix at extraction: such a claim MUST be backed by

  1. an EXPLICIT IN-SCOPE ENUMERATION — the concrete functions/modules that
     define "done" (several ``Function defined:`` / ``Class defined:`` /
     ``File exists:`` ACs, or an explicit ``In-scope:`` line), AND
  2. a spec-level OUT-OF-SCOPE block listing what is deliberately deferred.

A feature that cannot enumerate its in-scope surface is flagged not-ready for
decomposition or clarification rather than promoted with an unfalsifiable
"comprehensive" target.

Boundary: small, naturally-complete features (a single function, a 3-method
class) need no enumeration — the trigger is an unbounded scope word applied to
a *multi-item* surface, not every use of the word "all".

Integration: bob.spec_extractor.

Public API::

    from bob.scope_enumeration_linter import (
        check_scope_enumeration,
        has_unbounded_scope_word,
        ScopeEnumerationResult,
    )
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Unbounded scope vocabulary
# ---------------------------------------------------------------------------

# Multi-word phrases MUST be checked before bare words so the longest match
# wins ("all of" before "all", "100% parity" as a unit).
_UNBOUNDED_SCOPE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("100% parity", re.compile(r"\b100\s*%\s*parity\b", re.IGNORECASE)),
    ("full parity", re.compile(r"\bfull\s+parity\b", re.IGNORECASE)),
    ("all of", re.compile(r"\ball\s+of\b", re.IGNORECASE)),
    ("comprehensive", re.compile(r"\bcomprehensive\b", re.IGNORECASE)),
    ("complete", re.compile(r"\bcomplete\b", re.IGNORECASE)),
    ("everything", re.compile(r"\beverything\b", re.IGNORECASE)),
    ("entire", re.compile(r"\bentire\b", re.IGNORECASE)),
    ("full", re.compile(r"\bfull\b", re.IGNORECASE)),
]

# Signals that a surface is "large" (multi-item), i.e. enumeration is required.
_LARGE_SURFACE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bapi\s+surface\b", re.IGNORECASE),
    re.compile(r"\blibrary\b", re.IGNORECASE),
    re.compile(r"\bmodule[s]?\b", re.IGNORECASE),
    re.compile(r"\bparity\b", re.IGNORECASE),
    re.compile(r"\bwhole\b", re.IGNORECASE),
    re.compile(r"\bentire\b", re.IGNORECASE),
    re.compile(r"\ball\b", re.IGNORECASE),
    re.compile(r"\beverything\b", re.IGNORECASE),
    re.compile(r"\bfunctions\b", re.IGNORECASE),
    re.compile(r"\bclasses\b", re.IGNORECASE),
]

# Minimum number of enumerated in-scope items for a "large" surface to count
# as bounded. One or two items is naturally complete (single function / small
# class) and does not need enumeration.
_MIN_ENUMERATED_ITEMS = 3

# ACs that count as concrete in-scope enumeration entries.
_ENUMERATING_AC_RE = re.compile(
    r"^\s*(Function defined|Class defined|File exists|Field exists)\s*:",
    re.IGNORECASE,
)

_IN_SCOPE_RE = re.compile(r"\bin[\s-]scope\b", re.IGNORECASE)
_OUT_OF_SCOPE_RE = re.compile(r"\bout[\s-]of[\s-]scope\b", re.IGNORECASE)


@dataclass
class ScopeEnumerationResult:
    """Outcome of a scope-enumeration check for one feature."""

    feature_name: str = ""
    has_unbounded_scope: bool = False
    matched_word: str | None = None
    requires_enumeration: bool = False
    is_ready: bool = True
    issues: list[str] = field(default_factory=list)


def has_unbounded_scope_word(text: str) -> str | None:
    """Return the unbounded scope word/phrase found in *text*, else None.

    Detects "comprehensive", "full", "complete", "everything", "entire",
    "all of", "full parity", "100% parity". A bare "all" is deliberately NOT
    flagged (too many false positives, e.g. "returns all elements > x").

    Raises
    ------
    TypeError
        If *text* is not a string.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be a str, got {type(text).__name__}")
    for word, pattern in _UNBOUNDED_SCOPE_PATTERNS:
        if pattern.search(text):
            return word
    return None


def _is_large_surface(text: str) -> bool:
    """Return True if *text* describes a multi-item / large API surface."""
    return any(p.search(text) for p in _LARGE_SURFACE_PATTERNS)


def _count_enumerated_items(acceptance_criteria: list[str]) -> int:
    """Count concrete in-scope enumeration ACs."""
    return sum(1 for ac in acceptance_criteria if _ENUMERATING_AC_RE.match(str(ac)))


def _has_out_of_scope_block(feature_text: str, spec: dict[str, Any] | None) -> bool:
    """Return True if an out-of-scope block exists at spec or feature level."""
    if spec:
        for key in ("out_of_scope", "out-of-scope", "outOfScope"):
            val = spec.get(key)
            if val:
                return True
        preamble = spec.get("description") or spec.get("preamble") or ""
        if isinstance(preamble, str) and _OUT_OF_SCOPE_RE.search(preamble):
            return True
    return bool(_OUT_OF_SCOPE_RE.search(feature_text))


def check_scope_enumeration(
    feature: dict[str, Any],
    *,
    spec: dict[str, Any] | None = None,
) -> ScopeEnumerationResult:
    """Check that an unbounded-scope feature enumerates its in-scope surface.

    Parameters
    ----------
    feature:
        Feature dict with (at least) ``name``, ``description``, and
        ``acceptance_criteria`` keys.
    spec:
        Optional spec-level dict. An ``out_of_scope`` key (or an out-of-scope
        mention in the spec description/preamble) satisfies the spec-level
        out-of-scope requirement.

    Returns
    -------
    ScopeEnumerationResult
        ``is_ready`` is False when an unbounded word applies to a large surface
        without both an in-scope enumeration and an out-of-scope block.

    Raises
    ------
    TypeError
        If *feature* is not a dict, *spec* is not a dict/None, or
        ``acceptance_criteria`` is not a list.
    """
    if not isinstance(feature, dict):
        raise TypeError(f"feature must be a dict, got {type(feature).__name__}")
    if spec is not None and not isinstance(spec, dict):
        raise TypeError(f"spec must be a dict or None, got {type(spec).__name__}")

    acs = feature.get("acceptance_criteria") or []
    if not isinstance(acs, list):
        raise TypeError(
            f"acceptance_criteria must be a list, got {type(acs).__name__}"
        )

    name = str(feature.get("name") or "")
    description = str(feature.get("description") or "")
    combined = f"{name}\n{description}\n" + "\n".join(str(a) for a in acs)

    result = ScopeEnumerationResult(feature_name=name)

    matched = has_unbounded_scope_word(combined)
    if matched is None:
        return result  # bounded scope — always ready

    result.has_unbounded_scope = True
    result.matched_word = matched

    if not _is_large_surface(combined):
        # Unbounded word on a small, naturally-complete surface — no
        # enumeration required.
        return result

    result.requires_enumeration = True

    enumerated = _count_enumerated_items(acs)
    has_in_scope_line = bool(_IN_SCOPE_RE.search(combined))
    has_enumeration = enumerated >= _MIN_ENUMERATED_ITEMS or has_in_scope_line

    has_out_of_scope = _has_out_of_scope_block(combined, spec)

    if not has_enumeration:
        result.issues.append(
            f"Feature {name!r} claims unbounded scope ({matched!r}) over a large "
            f"surface but does not enumerate its in-scope items: provide at least "
            f"{_MIN_ENUMERATED_ITEMS} concrete 'Function defined:'/'Class defined:'/"
            f"'File exists:' ACs or an explicit 'In-scope:' list."
        )
    if not has_out_of_scope:
        result.issues.append(
            f"Feature {name!r} claims unbounded scope ({matched!r}) but the spec "
            f"carries no out-of-scope block listing what is deliberately deferred."
        )

    result.is_ready = not result.issues
    return result


__all__ = [
    "ScopeEnumerationResult",
    "check_scope_enumeration",
    "has_unbounded_scope_word",
]
