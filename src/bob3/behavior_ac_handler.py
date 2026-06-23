"""Behavior-AC handler: quoted-substring MUST-mention + MUST-NOT-use.

Provides entry points for verifying behavior ACs of the form:

    "behavior: ... MUST mention 'X' and MUST NOT use the phrase 'Y'"

The verifier previously hard-failed these ACs because they contain no
function identifier, F-RX-YYY token, or module path — only quoted literals.
This module extracts those literals and performs a workspace-wide
``src/**/*.py`` grep to verify presence/absence.

Public API
----------
extract_quoted_literals(criterion)
    Extract (must_mention, must_not_use) from an AC string.

verify_substring_presence(must_mention, must_not_use, workspace)
    Check extracted literals against workspace source files.
"""

from __future__ import annotations

import re
import pathlib
import logging

logger = logging.getLogger(__name__)

__all__ = [
    "extract_quoted_literals",
    "verify_substring_presence",
    "verify_behavior_ac_quoted_substring",
]


def extract_quoted_literals(criterion: str) -> tuple[str | None, str | None]:
    """Extract MUST-mention and MUST-NOT-use literals from a behavior AC string.

    Parses an AC of the form:
        "... MUST mention 'X' and MUST NOT use the phrase 'Y'"

    Parameters
    ----------
    criterion:
        Full AC criterion text.

    Returns
    -------
    tuple[str | None, str | None]
        ``(must_mention, must_not_use)`` — either may be ``None``.
    """
    _mention_m = re.search(
        r"MUST\s+(?:mention|contain|include|say|emit|use|have)\s+['\"]([^'\"]+)['\"]",
        criterion,
        re.IGNORECASE,
    )
    _forbid_m = re.search(
        r"MUST\s+NOT\s+(?:mention|contain|include|say|emit|use|have)"
        r"\s+(?:the\s+(?:phrase|string|substring|literal)\s+)?['\"]([^'\"]+)['\"]",
        criterion,
        re.IGNORECASE,
    )
    must_mention = _mention_m.group(1) if _mention_m else None
    must_not_use = _forbid_m.group(1) if _forbid_m else None
    return must_mention, must_not_use


def verify_substring_presence(
    must_mention: str | None,
    must_not_use: str | None,
    workspace: pathlib.Path,
) -> bool | None:
    """Check MUST-mention / MUST-NOT-use literal constraints against the workspace.

    Scans ``workspace/src/**/*.py`` for the given literals.

    Parameters
    ----------
    must_mention:
        Substring that must be present in at least one ``.py`` file, or
        ``None`` to skip the presence check.
    must_not_use:
        Substring that must be absent from all ``.py`` files, or ``None``
        to skip the absence check.
    workspace:
        Project root directory.

    Returns
    -------
    bool | None
        ``True`` if constraints satisfied, ``None`` if no evidence found.
    """
    if must_mention is None and must_not_use is None:
        return None

    _src_root = workspace / "src"
    _mention_hit = False
    _forbid_hit = False

    if _src_root.exists():
        for _p in _src_root.rglob("*.py"):
            try:
                _txt = _p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if must_mention and (must_mention in _txt):
                _mention_hit = True
            if must_not_use and (must_not_use in _txt):
                _forbid_hit = True

    _mention_ok = (must_mention is None) or _mention_hit
    _forbid_ok = (must_not_use is None) or (not _forbid_hit)

    if _mention_ok and _forbid_ok:
        return True
    return None


def verify_behavior_ac_quoted_substring(
    criterion: str,
    workspace: pathlib.Path,
) -> bool | None:
    """Verify a behavior AC containing MUST-mention / MUST-NOT-use quoted literals.

    Extracts quoted literals from *criterion* using :func:`extract_quoted_literals`
    then checks them via :func:`verify_substring_presence`.

    Parameters
    ----------
    criterion:
        Full AC text (behavior or structural).
    workspace:
        Project root directory.

    Returns
    -------
    bool | None
        ``True`` if constraints satisfied, ``None`` if no literals found.
        Never raises for ``str`` input.

    Raises
    ------
    ValueError
        When *criterion* is not a ``str``.
    """
    if not isinstance(criterion, str):
        raise ValueError(
            f"verify_behavior_ac_quoted_substring: criterion must be a str, "
            f"got {type(criterion).__name__!r}"
        )
    must_mention, must_not_use = extract_quoted_literals(criterion)
    if must_mention is None and must_not_use is None:
        return None
    result = verify_substring_presence(must_mention, must_not_use, workspace)
    if result is None and must_mention is not None:
        logger.warning(
            "BEHAVIOR_AC_SUBSTRING_DEMOTION: must-mention literal %r not found "
            "in workspace src/**/*.py; criterion=%s",
            must_mention,
            criterion,
        )
    return result
