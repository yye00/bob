"""Structural log-line AC handler — "X.py emits a 'STRING' log line".

Canonical entry point for the ``match_log_line_ac`` function which tolerates
Python adjacent-string-literal concat across newlines.  The underlying
three-tier search algorithm lives in
``bob.enhanced_verification.handle_structural_log_line``; this module
re-exports it under the name required by the AC spec.
"""

from __future__ import annotations

import pathlib

from bob.enhanced_verification import handle_structural_log_line

__all__ = ["match_log_line_ac"]


def match_log_line_ac(
    criterion_body: str,
    workspace: pathlib.Path,
) -> bool | None:
    """Handle structural ACs of the form "X.py emits a 'STRING' log line".

    Tolerates Python adjacent-string-literal concat across newlines so that
    a log format string split over two adjacent literals is still found.

    Delegates to ``bob.enhanced_verification.handle_structural_log_line``
    which implements the three-tier search:

    1. Exact match in raw file content.
    2. Adjacent-literal join: strip adjacent-literal seams and re-search.
    3. Token-order fallback: all whitespace-separated tokens of STRING present
       in joined content → PASS with WARNING.

    Parameters
    ----------
    criterion_body:
        The AC text after stripping the ``structural:`` prefix, e.g.
        ``"src/bob/run_loop.py emits a 'Run finished: termination=%s' log line"``.
    workspace:
        Project root ``pathlib.Path``.

    Returns
    -------
    bool | None
        ``True`` — log line confirmed (exact, adjacent-join, or token-order pass).
        ``None`` — criterion does not match the "emits" pattern or string not found;
        caller should fall through to the next handler.

    Raises
    ------
    ValueError
        If ``criterion_body`` is not a ``str`` or ``workspace`` is not a
        ``pathlib.Path``.
    """
    return handle_structural_log_line(
        criterion_body=criterion_body,
        workspace=workspace,
    )
