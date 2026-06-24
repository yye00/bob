"""Structural log-line AC handler for acceptance_criteria package.

"X.py emits a 'STRING' log line" — tolerates Python adjacent-string-literal
concat across newlines.
"""

from __future__ import annotations

import pathlib

from bob3.enhanced_verification import handle_structural_log_line

__all__ = ["match_structural_log_line"]


def match_structural_log_line(
    criterion_body: str,
    workspace: pathlib.Path,
) -> bool | None:
    """Handle structural ACs of the form "X.py emits a 'STRING' log line".

    Tolerates Python adjacent-string-literal concat across newlines so that
    a log format string split over two adjacent literals is still found.

    Delegates to ``bob3.enhanced_verification.handle_structural_log_line``
    which implements the three-tier search:

    1. Exact match in raw file content.
    2. Adjacent-literal join: strip adjacent-literal seams and re-search.
    3. Token-order fallback: all whitespace-separated tokens of STRING present
       in joined content → PASS with WARNING.

    Parameters
    ----------
    criterion_body:
        The AC text after stripping the ``structural:`` prefix.
    workspace:
        Project root ``pathlib.Path``.

    Returns
    -------
    bool | None
        ``True`` if the log line is confirmed; ``None`` if not matched or not
        found.

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
