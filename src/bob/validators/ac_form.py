"""bob.validators.ac_form — AC-form validator for planning time.

Validates that every acceptance criterion matches the canonical grammar
before a feature is persisted to the database. Prevents the v.13 class of
parser bugs (Function-defined parenthetical descriptions, pytest-AC trailing
prose, pytest_scoper module-seed parens) at the source.

Canonical AC forms accepted:
  File exists: <path>
  Function defined: <dotted.path>
  Class defined: <dotted.path>
  pytest: <test_path>
  integration: <dotted.module>
  behavior: <subject> <verb> <object> when <condition>  (EARS-style)

Each form has a strict terminal structure — no trailing parenthetical
descriptions, em-dash prose, or unprefixed text after the canonical value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["validate_acceptance_criteria", "parse_criterion", "MalformedACError"]


# ---------------------------------------------------------------------------
# Grammar: each entry is (human_name, regex that must match the full stripped AC)
# ---------------------------------------------------------------------------

# pytest: <path> — path may contain /, -, _, ., ::  but NO spaces, parens,
# em-dashes, or trailing prose. The v.13 regression was exactly trailing prose
# after a space or em-dash.
_PYTEST_RE = re.compile(r"^pytest\s*:\s*[^\s()]+$", re.IGNORECASE)

# File exists: <path> — any non-whitespace path, no trailing prose/parens.
_FILE_EXISTS_RE = re.compile(r"^File\s+exists\s*:\s*\S+$", re.IGNORECASE)

# Function defined: <dotted.path> — dotted identifier only, no parens or prose.
# The v.13 regression was "Function defined: mod.fn (description in parens)".
_FUNCTION_DEFINED_RE = re.compile(r"^Function\s+defined\s*:\s*[\w][\w.]*$", re.IGNORECASE)

# Class defined: <dotted.path>
_CLASS_DEFINED_RE = re.compile(r"^Class\s+defined\s*:\s*[\w][\w.]*$", re.IGNORECASE)

# integration: <dotted.module.or.path> — may contain . / : - but no spaces.
_INTEGRATION_RE = re.compile(r"^integration\s*:\s*[\w][\w./:-]*$", re.IGNORECASE)

# behavior: <EARS clause> — must contain 'when' somewhere after the prefix.
_BEHAVIOR_RE = re.compile(r"^behavior\s*:\s*.+\bwhen\b.+$", re.IGNORECASE)

_COMMAND_RE = re.compile(r"^command(?:\s+succeeds)?\s*:\s*\S.*", re.IGNORECASE)
_BUILD_RE = re.compile(r"^(?:build|compile|link)\s*:\s*\S.*", re.IGNORECASE)
_CTEST_RE = re.compile(r"^ctest\s*:\s*\S.*", re.IGNORECASE)

_CANONICAL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("pytest", _PYTEST_RE),
    ("File exists", _FILE_EXISTS_RE),
    ("Function defined", _FUNCTION_DEFINED_RE),
    ("Class defined", _CLASS_DEFINED_RE),
    ("integration", _INTEGRATION_RE),
    ("behavior (EARS)", _BEHAVIOR_RE),
    ("command", _COMMAND_RE),
    ("build", _BUILD_RE),
    ("ctest", _CTEST_RE),
]


@dataclass
class _MalformedEntry:
    index: int
    criterion: str
    reason: str


def _classify(ac: str) -> str | None:
    """Return None if ac matches a canonical form, else a reason string."""
    stripped = ac.strip()

    if not stripped:
        return "empty or whitespace-only criterion — no measurable outcome"

    for _name, pattern in _CANONICAL_PATTERNS:
        if pattern.match(stripped):
            return None

    # Produce a targeted reason for the v.13 regression patterns.
    stripped_lower = stripped.lower()

    if stripped_lower.startswith("pytest:") or stripped_lower.startswith("pytest :"):
        return (
            "malformed pytest: AC — trailing prose or parenthetical after the test path is not allowed "
            "(v.13 regression: 'pytest: path — description' or 'pytest: path (note)')"
        )
    if stripped_lower.startswith("function defined:") or stripped_lower.startswith("function defined :"):
        return (
            "malformed Function defined: AC — only a bare dotted identifier is accepted; "
            "no parenthetical descriptions allowed "
            "(v.13 regression: 'Function defined: mod.fn (description)')"
        )
    if stripped_lower.startswith("file exists:") or stripped_lower.startswith("file exists :"):
        return "malformed File exists: AC — path must be a single non-whitespace token with no trailing prose"
    if stripped_lower.startswith("class defined:") or stripped_lower.startswith("class defined :"):
        return "malformed Class defined: AC — only a bare dotted identifier is accepted"
    if stripped_lower.startswith("integration:") or stripped_lower.startswith("integration :"):
        return "malformed integration: AC — module path must contain no spaces or trailing prose"
    if stripped_lower.startswith("behavior:") or stripped_lower.startswith("behavior :"):
        return "malformed behavior: AC — must follow EARS form: 'behavior: <subject> <verb> <object> when <condition>'"

    return (
        "does not match any canonical AC form: "
        "'File exists: <path>', 'Function defined: <dotted.path>', "
        "'Class defined: <dotted.path>', 'pytest: <test_path>', "
        "'integration: <dotted.module>', or "
        "'behavior: <subject> <verb> <object> when <condition>'"
    )


def parse_criterion(ac: str) -> dict[str, str]:
    """Parse a single acceptance criterion into its type and value.

    Parameters
    ----------
    ac:
        A single acceptance criterion string.

    Returns
    -------
    dict with keys ``type`` (canonical prefix name) and ``value`` (the payload).

    Raises
    ------
    ValueError
        When the criterion does not match any canonical form.
    """
    stripped = ac.strip()
    reason = _classify(stripped)
    if reason is not None:
        raise ValueError(f"malformed acceptance criterion {stripped!r}: {reason}")

    for name, pattern in _CANONICAL_PATTERNS:
        if pattern.match(stripped):
            # Extract payload: everything after the first colon and optional whitespace.
            colon_pos = stripped.index(":")
            value = stripped[colon_pos + 1 :].strip()
            return {"type": name, "value": value}

    # Unreachable if _classify returned None, but satisfies type checker.
    raise ValueError(f"malformed acceptance criterion {stripped!r}")  # pragma: no cover


def validate_acceptance_criteria(criteria: list[str]) -> list[str]:
    """Validate every acceptance criterion against the canonical grammar.

    Run at ``bob plan --create`` time to reject malformed ACs before
    the feature is persisted to the database.

    Parameters
    ----------
    criteria:
        List of acceptance criterion strings to validate.

    Returns
    -------
    list[str]
        An empty list when all criteria are well-formed.

    Raises
    ------
    ValueError
        When one or more criteria are malformed. The error message names
        every offending criterion and its index so the author can correct
        them before re-submitting.
    """
    if not isinstance(criteria, list):
        raise TypeError(
            f"validate_acceptance_criteria expects a list of strings, "
            f"got {type(criteria).__name__!r}"
        )

    malformed: list[_MalformedEntry] = []

    for idx, ac in enumerate(criteria):
        reason = _classify(ac)
        if reason is not None:
            malformed.append(_MalformedEntry(index=idx, criterion=ac, reason=reason))

    if not malformed:
        return []

    lines = ["malformed acceptance criteria — fix before persisting to DB:", ""]
    for entry in malformed:
        lines.append(f"  [{entry.index}] {entry.criterion!r}")
        lines.append(f"       reason: {entry.reason}")
        lines.append("")

    raise ValueError("\n".join(lines).rstrip())


# Expose a typed alias for callers that want to catch only this validator's errors.
MalformedACError = ValueError
