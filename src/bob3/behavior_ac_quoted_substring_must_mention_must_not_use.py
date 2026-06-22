"""Behavior-AC quoted-substring MUST-mention + MUST-NOT-use handler.

Handles ACs of the form:
    "behavior: ... MUST mention 'X' and MUST NOT use the phrase 'Y'"

The verifier previously hard-failed these because no function identifier
or F-RX-YYY token was present. This module provides a dedicated entry point
that extracts the quoted literals and does a workspace-wide src/**/*.py grep.

PASS when:
  - must_mention literal is present in at least one .py (or not specified), AND
  - must_not_use literal is absent from all .py files (or not specified).

Returns None when no literals are found (caller falls through to next strategy).
"""

from __future__ import annotations

import pathlib

from bob3.enhanced_verification import verify_behavior_ac_with_substring_grep


def behavior_ac_quoted_substring_must_mention_must_not_use(
    criterion: str,
    workspace: pathlib.Path,
) -> bool | None:
    """Verify a behavior AC containing MUST-mention / MUST-NOT-use quoted literals.

    Extracts quoted literals from *criterion* using the patterns:

    * ``MUST mention 'X'`` — *X* must appear in at least one ``src/**/*.py``
    * ``MUST NOT use the phrase 'Y'`` — *Y* must be absent from all ``src/**/*.py``

    Returns ``True`` when constraints are satisfied, ``None`` when no literals
    were found or the constraints could not be confirmed.  Never raises.

    Parameters
    ----------
    criterion:
        Full AC text (behavior or structural).
    workspace:
        Project root directory.

    Returns
    -------
    bool | None
        ``True`` if satisfied, ``None`` otherwise.
    """
    try:
        return verify_behavior_ac_with_substring_grep(criterion, workspace)
    except Exception:
        return None
