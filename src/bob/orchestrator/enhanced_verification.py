"""Structural log-line AC handler for bob.orchestrator.

Provides ``verify_structural_log_line`` — a thin wrapper around
``bob.enhanced_verification.handle_structural_log_line`` that tolerates
Python adjacent-string-literal concat across newlines when verifying ACs
of the form ``"X.py emits a 'STRING' log line"``.

Feature: 0a898414-1b37-4a43-b65b-a2f7a447abd0
"""

from __future__ import annotations

import pathlib

from bob.enhanced_verification import handle_structural_log_line


def verify_structural_log_line(
    *,
    criterion_body: str,
    workspace: pathlib.Path,
) -> bool | None:
    """Verify a structural "X.py emits a 'STRING' log line" acceptance criterion.

    Delegates to ``handle_structural_log_line`` which tolerates Python
    adjacent-string-literal concat across newlines.

    Args:
        criterion_body: AC text, e.g. ``"src/bob/run_loop.py emits a
            'Run finished: termination=%s' log line"``.
        workspace: Project root ``pathlib.Path``.

    Returns:
        ``True`` if confirmed, ``None`` if no match or string not found.

    Raises:
        ValueError: If ``criterion_body`` is not a str or ``workspace`` is
            not a ``pathlib.Path``.
    """
    return handle_structural_log_line(
        criterion_body=criterion_body,
        workspace=workspace,
    )


def check_structural_log_line_ac(
    *,
    criterion_body: str,
    workspace: pathlib.Path,
) -> bool | None:
    """Check a structural "X.py emits a 'STRING' log line" acceptance criterion.

    Public entry point for feature badf78e8. Delegates to
    ``bob.enhanced_verification.handle_structural_log_line`` which tolerates
    Python adjacent-string-literal concat across newlines (a log format string
    split across two adjacent literals separated by whitespace + newline).

    Args:
        criterion_body: AC text after stripping any ``structural:`` prefix,
            e.g. ``"src/bob/orchestrator/run_loop.py emits a 'Run finished:
            termination=%s' log line"``.
        workspace: Project root ``pathlib.Path``.

    Returns:
        ``True`` if the log line is confirmed (verbatim, adjacent-literal
        joined, or token-order demoted), ``None`` if the criterion does not
        match the "emits" pattern or the log string is not found.

    Raises:
        ValueError: If ``criterion_body`` is not a str or ``workspace`` is not
            a ``pathlib.Path``.
    """
    return handle_structural_log_line(
        criterion_body=criterion_body,
        workspace=workspace,
    )
