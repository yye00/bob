"""Behavior-AC quoted-substring MUST-mention + MUST-NOT-use verifier.

Public entry point for verifying behavior ACs that assert literal string
presence/absence with no function identifier.  Wraps the implementation in
:mod:`bob3.enhanced_verification` under the canonical name required by
the feature acceptance criteria.
"""

from __future__ import annotations

import pathlib

from bob3.enhanced_verification import (
    extract_quoted_literals,
    verify_quoted_substring_ac as _verify_quoted_substring_ac,
)

__all__ = ["verify_quoted_substring_ac", "extract_quoted_literals"]


def verify_quoted_substring_ac(
    criterion: str,
    workspace: pathlib.Path,
) -> bool | None:
    """Verify a behavior AC containing MUST-mention / MUST-NOT-use quoted literals.

    Extracts quoted literals from *criterion* and scans ``workspace/src/**/*.py``:

    * PASS (``True``) when the must-mention literal is present in at least one
      file AND the must-not-use literal is absent from all files.
    * ``None`` when no literals are found (caller should fall through).

    Raises ``ValueError`` when *criterion* is not a ``str``.

    Parameters
    ----------
    criterion:
        Full AC text (behavior or structural).
    workspace:
        Project root directory.

    Returns
    -------
    bool | None
        ``True`` if satisfied, ``None`` if no literals found / constraints
        unverifiable.

    Raises
    ------
    ValueError
        When *criterion* is not a ``str`` instance.
    """
    return _verify_quoted_substring_ac(criterion, workspace)
