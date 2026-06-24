"""Structural log-line AC handler for bob verification.

Provides ``match_log_line_ac`` — a thin public alias over
``bob.enhanced_verification.handle_structural_log_line`` — so that ACs of the
form::

    Function defined: bob.verification.structural_log_handler.match_log_line_ac

are satisfiable from the ``bob.verification`` namespace without duplicating
logic.

The underlying implementation tolerates Python adjacent-string-literal
concatenation across newlines, e.g.::

    logger.info(
        "Run finished: termination=%s features_completed=%d "
        "features_failed=%d ..."
    )

A naive ``STRING in file_contents`` check misses this because the file text
has a closing ``"..."``, whitespace, newline, and another opening ``"..."``
between the two halves.  The handler normalises those seams and falls back to
token-order matching before giving up.
"""

from __future__ import annotations

import pathlib

from bob.enhanced_verification import handle_structural_log_line


def match_log_line_ac(
    *,
    criterion_body: str,
    workspace: pathlib.Path,
) -> bool | None:
    """Return True if *criterion_body* names a log line present in the workspace file.

    Delegates to :func:`bob.enhanced_verification.handle_structural_log_line`
    which implements the three-stage algorithm:

    1. Exact match in raw source.
    2. Adjacent-literal join (``['"]\\ *\\n\\ *['"]`` removed) then search.
    3. Token-order fallback: all whitespace-separated tokens present → PASS
       with WARNING.
    4. Miss → ``None`` (caller falls through to next handler).

    Args:
        criterion_body: AC text *after* stripping the ``structural:`` prefix,
            e.g. ``"src/bob/run_loop.py emits a 'Run finished:
            termination=%s' log line"``.
        workspace: Project root as a :class:`pathlib.Path`.

    Returns:
        ``True`` if confirmed (or token-order demoted to PASS), ``None``
        if the criterion does not match the "emits" pattern or the string is
        absent.

    Raises:
        ValueError: if *criterion_body* is not a ``str`` or *workspace* is not
            a :class:`pathlib.Path`.
    """
    return handle_structural_log_line(
        criterion_body=criterion_body,
        workspace=workspace,
    )


__all__ = ["match_log_line_ac"]
