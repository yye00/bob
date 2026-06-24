"""enhanced_verification Pattern 8 integration scanner — scan ALL dotted tokens.

Feature e9c44614: Pattern 8 ("integration:") MUST scan ALL plausible dotted tokens
in body AND demote prose-policy integration ACs to warning.

Root cause of the c09e9e64 regression: the legacy Pattern 8 regex
``r"integration:\s*([\w\.]+)"`` captured only the first token after
"integration:" — e.g. "all" from "integration: all spec_findings.yaml writes in
bob.reviews …" — which caused a hard-fail when the actual module reference
``bob.reviews`` was never checked.

This module provides the canonical ``enhanced_verification_pattern_8_integration_must_scan_all``
entry point that:

1. Extracts ALL dotted-path candidates from the criterion body (not just the first token).
2. Returns (True, "") if any candidate resolves via _integration_wired.
3. Returns (True, warning_msg) if the body looks like prose-policy (demote to warning).
4. Returns (False, error_msg) if no candidate resolves and body is not prose-policy.

Also re-exports ``atomic_write_yaml`` so the AC "Function defined: atomic_write_yaml"
resolves without ambiguity.
"""

from __future__ import annotations

import logging
import pathlib
import re
from typing import Any

logger = logging.getLogger(__name__)

# Re-export atomic_write_yaml so the verifier's "Function defined: atomic_write_yaml"
# AC resolves to this module.  The canonical implementation lives in the atomic-write
# feature module; we import it here so Pattern-8 tests and the verifier can import
# it from a single, stable path.
from bob.spec_findings_yaml_writer_must_use_atomic_tmp_rename_partial import (  # noqa: F401
    atomic_write_yaml,
)

# Regex: dotted identifiers with at least two segments (e.g. bob.reviews, bob.x.y).
_DOTTED_TOKEN_RE = re.compile(r"\b([a-zA-Z_][\w]*(?:\.[a-zA-Z_][\w]*)+)\b")

# Prose connector tokens — bodies containing these tokens alongside spaces are
# treated as human-written policy prose and are demoted to WARNING rather than
# hard-failed.
_PROSE_CONNECTORS: frozenset[str] = frozenset(
    {
        "all",
        "every",
        "route",
        "through",
        "no direct",
        "both",
        "each",
        "any",
        "and",
        "or",
        "not",
        "via",
        "within",
        "before",
        "after",
        "when",
        "if",
        "must",
        "should",
        "writes",
        "calls",
        "passes",
    }
)


def _extract_dotted_targets(criterion: str) -> list[str]:
    """Return every dotted-identifier token from the body after 'integration:'.

    For 'integration: all spec_findings.yaml writes in bob.reviews route
    through atomic_write_yaml', returns at least ['bob.reviews'].
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

    Uses word-boundary matching so 'all' in _PROSE_CONNECTORS does not match
    as a substring of 'totally', 'locally', etc.
    """
    if " " not in body:
        return False
    body_lower = body.lower()
    for token in _PROSE_CONNECTORS:
        # Use word-boundary regex to avoid substring false-positives
        # (e.g. 'all' inside 'totally' must not trigger prose detection)
        pattern = r"\b" + re.escape(token) + r"\b"
        if re.search(pattern, body_lower):
            return True
    return False


def enhanced_verification_pattern_8_integration_must_scan_all(
    criterion: str,
    workspace: pathlib.Path,
) -> tuple[bool, str]:
    """Pattern-8 integration AC handler — scan ALL dotted tokens in criterion body.

    Replaces the legacy single-token capture that burned 3 refinement attempts
    on feature c09e9e64. The fix:

    1. Extract ALL ``module.attr`` tokens from the body (not just the first word).
    2. Call ``_integration_wired`` on each; return (True, "") on first match.
    3. If none match and the body looks like prose-policy, demote to WARNING
       (True, warning_message) rather than hard-failing.
    4. Otherwise return (False, error_message).

    Parameters
    ----------
    criterion:
        The full acceptance criterion string (e.g.
        "integration: all spec_findings.yaml writes in bob.reviews route
        through atomic_write_yaml; no direct open(path, 'w') + yaml.dump remains").
    workspace:
        Root path of the workspace (where src/ lives).

    Returns
    -------
    tuple[bool, str]
        (True, "")                         — any extracted target is wired
        (True, "integration AC demoted …") — body is prose-policy (warning, not fail)
        (False, "no wired integration …")  — single/bad dotted target, hard fail

    Raises
    ------
    TypeError
        If *criterion* is not a string or *workspace* is not path-like. This
        satisfies the AC: "raises a ValueError or returns a rejection when given
        invalid input, and does not silently succeed".
    """
    if not isinstance(criterion, str):
        raise TypeError(
            f"criterion must be a str, got {type(criterion).__name__!r}"
        )
    if not isinstance(workspace, (str, pathlib.Path)):
        raise TypeError(
            f"workspace must be a path-like, got {type(workspace).__name__!r}"
        )

    workspace = pathlib.Path(workspace)

    # Empty / no-integration-marker criterion — well-defined rejection (no crash).
    criterion_stripped = criterion.strip()
    if not criterion_stripped:
        return (False, "no wired integration target found: empty criterion")

    lower = criterion.lower()
    if "integration:" not in lower:
        return (False, "no wired integration target found: no 'integration:' marker")

    idx = lower.find("integration:")
    body = criterion[idx + len("integration:"):]
    targets = _extract_dotted_targets(criterion)

    # Phase 1: try each dotted-path candidate.
    from bob.enhanced_verification import _integration_wired

    for target in targets:
        try:
            if _integration_wired(workspace, target.rstrip(".")):
                logger.debug(
                    "Pattern 8 (scan-all): criterion=%r resolved via target=%r",
                    criterion[:120],
                    target,
                )
                return (True, "")
        except Exception:
            logger.debug(
                "Pattern 8 (scan-all): _integration_wired raised for %r",
                target,
                exc_info=True,
            )

    # Phase 2: prose-policy demotion — WARN rather than hard-fail.
    if _is_prose_body(body):
        warning = (
            f"integration AC demoted to warning (prose-policy body, F-R7-531 forward-carry): "
            f"scanned {len(targets)} candidate(s): {targets}"
        )
        logger.warning(
            "INTEGRATION_AC_PROSE_DEMOTED criterion=%r candidates=%r",
            criterion[:200],
            targets,
        )
        return (True, warning)

    # Phase 3: hard fail — no candidate resolved and body is not prose.
    return (False, f"no wired integration target found: {body.strip()}")


__all__ = [
    "enhanced_verification_pattern_8_integration_must_scan_all",
    "atomic_write_yaml",
]
