"""Subagent self-verification must use scoped pytest, not the full suite.

Subagents instructed to run ``python -m pytest tests/ -v`` run the full
1800+ test suite, taking >30 min and triggering max_turns cancellation
before they can mark their feature complete. This module provides the
canonical function that returns a scoped pytest invocation string based
on the feature's own ``pytest:`` ACs instead of the full suite root.

Public API
----------
subagent_self_verification_must_use_scoped_pytest_not_full(feature_id, acceptance_criteria)
    Return a scoped ``python -m pytest <paths> -v`` string derived from
    the feature's own ``pytest:`` ACs. Returns an empty string when no
    ``pytest:`` ACs are present so the caller can skip pytest rather than
    falling back to the full-suite command.
"""

from __future__ import annotations

from bob3.superpowers import extract_pytest_paths

__all__ = ["subagent_self_verification_must_use_scoped_pytest_not_full"]


def subagent_self_verification_must_use_scoped_pytest_not_full(
    feature_id: str,
    acceptance_criteria: list[str] | None = None,
) -> str:
    """Return a scoped pytest command string for *feature_id*'s own tests.

    Scans *acceptance_criteria* for ``pytest:``-prefixed entries and builds
    a ``python -m pytest <paths> -v`` string covering only those paths.
    Returns an empty string when no ``pytest:`` ACs are present so callers
    can skip pytest rather than inadvertently running the full suite.

    Args:
        feature_id:          The feature's UUID (included for call-site
                             readability; not used in path extraction).
        acceptance_criteria: Optional list of AC strings from the feature's
                             ``acceptance_criteria`` field.  Items starting
                             with ``pytest:`` contribute path tokens.

    Returns:
        A ``python -m pytest <paths> -v`` string, or ``""`` when no
        ``pytest:`` ACs are found.  Never returns the full-suite command
        ``python -m pytest tests/ -v``.
    """
    paths = extract_pytest_paths(acceptance_criteria)
    if not paths:
        return ""
    return "python -m pytest " + " ".join(paths) + " -v"
