"""Verification utilities for scoped subagent self-verification.

Subagents MUST run only the ``pytest:``-scoped test files extracted from
their own feature's acceptance criteria instead of the full ``tests/`` suite
root.  The full suite has 1800+ tests and takes >30 minutes; running it via
a subagent will exhaust max_turns before the agent can report completion.

This module provides :func:`extract_pytest_ac_paths` as the canonical
extraction function so that orientation prompts can reference it by its
fully-qualified name ``superpowers.verification.extract_pytest_ac_paths``.
"""

from __future__ import annotations


def extract_pytest_ac_paths(acceptance_criteria: list[str] | None) -> list[str]:
    """Extract path tokens from ``pytest:``-prefixed acceptance criteria.

    Scans *acceptance_criteria* for items whose prefix (case-insensitive) is
    ``"pytest:"`` and returns the trailing path token from each.  Empty paths
    are omitted.  Subagents should pass only these paths to pytest during
    self-verification rather than pointing pytest at the full ``tests/`` root.

    Args:
        acceptance_criteria: List of AC strings, or ``None``.  Passing
            ``None`` or an empty list returns an empty list without raising.

    Returns:
        List of path strings (e.g. ``["tests/test_foo.py"]``), in the order
        they appear in *acceptance_criteria*.  Empty when no ``pytest:`` ACs
        are present.

    Raises:
        ValueError: If *acceptance_criteria* is not a list or ``None``, or if
            any list item is not a string — callers typically have a bug when
            they pass a non-list scalar (e.g. a raw JSON string).

    Examples:
        >>> extract_pytest_ac_paths(None)
        []
        >>> extract_pytest_ac_paths([])
        []
        >>> extract_pytest_ac_paths(["pytest: tests/test_foo.py", "File exists: src/foo.py"])
        ['tests/test_foo.py']
        >>> extract_pytest_ac_paths(["PYTEST: tests/test_upper.py"])
        ['tests/test_upper.py']
    """
    if acceptance_criteria is None:
        return []
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list or None, "
            f"got {type(acceptance_criteria).__name__!r}"
        )
    paths: list[str] = []
    for i, ac in enumerate(acceptance_criteria):
        if not isinstance(ac, str):
            raise ValueError(
                f"acceptance_criteria items must be strings, "
                f"got {type(ac).__name__!r} at index {i}: {ac!r}"
            )
        stripped = ac.strip()
        if stripped.lower().startswith("pytest:"):
            path = stripped[len("pytest:"):].strip()
            # Strip any trailing description text after a " — " separator
            # e.g. "tests/test_foo.py — empty, zero, or minimum input…"
            if " — " in path:
                path = path.split(" — ", 1)[0].strip()
            elif " -- " in path:
                path = path.split(" -- ", 1)[0].strip()
            if path:
                paths.append(path)
    return paths
