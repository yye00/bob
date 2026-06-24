"""Structural log-line AC handler — "X.py emits a 'STRING' log line" (feature f78ce68d).

Problem (bob3 v.20 r1, 2026-06-01)
------------------------------------
Feature 6fc999b8 (F-R7-586 ALL_BLOCKED rename) failed 2/6 ACs despite the
implementation being correct.  The run_loop.py log format string was split
across Python adjacent-string-literal concat::

    logger.info(
        "Run finished: termination=%s features_completed=%d "
        "features_failed=%d ..."
    )

A naive ``STRING in file_contents`` check missed the log string because the raw
file text contains ``"..." NEWLINE "..."`` between the two halves.  Existing
structural handlers only recognised "X.py defines function Y" — log-line ACs
fell through to F-R7-582 which cannot match string literals.

Fix (F-R7-590, bob3 version 20)
---------------------------------
``handle_structural_log_line`` in ``bob3.enhanced_verification`` implements the
three-tier search:

1. Exact match in raw file content.
2. Adjacent-literal join: strip ``['"]\\s*\\n\\s*['"]`` seams, re-search.
3. Token-order fallback: all whitespace tokens of STRING present in joined
   content → PASS with WARNING.

This module is the canonical delegation entry point that surfaces the rule in
the bob3 spec. The underlying logic lives in
``bob3.enhanced_verification.handle_structural_log_line``.
"""

from __future__ import annotations

import pathlib

from bob3.enhanced_verification import handle_structural_log_line

__all__ = ["structural_log_line_ac_handler_x_py_emits_string_log_line"]


def structural_log_line_ac_handler_x_py_emits_string_log_line(
    criterion_body: str,
    workspace: pathlib.Path,
) -> bool | None:
    """Handle structural ACs of the form "X.py emits a 'STRING' log line".

    Tolerates Python adjacent-string-literal concat across newlines so that
    a log format string split over two adjacent literals is still found.

    Parameters
    ----------
    criterion_body:
        The AC text *after* stripping the ``structural:`` prefix, e.g.
        ``"src/bob3/run_loop.py emits a 'Run finished: termination=%s' log line"``.
    workspace:
        Project root ``pathlib.Path``.

    Returns
    -------
    bool | None
        ``True`` — log line confirmed (exact, adjacent-join, or token-order pass).
        ``None`` — criterion does not match the "emits" pattern or string not found;
        caller should fall through to the next handler.
    """
    return handle_structural_log_line(
        criterion_body=criterion_body,
        workspace=workspace,
    )
