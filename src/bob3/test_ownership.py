"""Test ownership declarations for bob3 features.

Feature 9d81f623-6e65-48c7-a0af-816db1bfebc9

Every feature MUST declare which test files it owns.  Regression demotion
MUST require evidence that the feature's own tests newly fail — no scapegoating.

This module provides ``declare_test_ownership`` to register ownership and
utilities to query that ownership at verification time.
"""

from __future__ import annotations

import json
import re

__all__ = [
    "declare_test_ownership",
    "get_feature_test_files",
]

_PYTEST_AC_RE = re.compile(r"^\s*pytest\s*:\s*(.+?)(?:\s+—.*)?$", re.IGNORECASE)


def _parse_ac_list(raw: object) -> list[str]:
    if isinstance(raw, list):
        return [str(ac) for ac in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(ac) for ac in parsed]
        except (json.JSONDecodeError, ValueError):
            pass
        return [line.strip() for line in raw.splitlines() if line.strip()]
    return []


def declare_test_ownership(
    *,
    feature_id: str,
    test_files: list[str] | None,
) -> dict[str, list[str]]:
    """Declare that *feature_id* owns the given *test_files*.

    Every feature must call this (or equivalent) to register which test files
    it owns.  The ownership declaration is required before any regression
    demotion can be applied — a feature with no declared test ownership cannot
    be scapegoated for failing tests it never claimed.

    Args:
        feature_id: Non-empty string identifying the feature.
        test_files: List of test file paths the feature owns.  May be empty
            but must not be None.

    Returns:
        ``{feature_id: [test_file, ...]}`` — a dict mapping the feature to
        its declared test files.

    Raises:
        ValueError: When *feature_id* is an empty string.
        TypeError: When *feature_id* is None, not a string, or *test_files*
            is None, not a list, or contains non-string entries.
    """
    if feature_id is None:
        raise TypeError("feature_id must not be None")
    if not isinstance(feature_id, str):
        raise TypeError(f"feature_id must be a string, got {type(feature_id)!r}")
    if not feature_id:
        raise ValueError("feature_id must not be an empty string")
    if test_files is None:
        raise TypeError("test_files must not be None")
    if not isinstance(test_files, list):
        raise TypeError(f"test_files must be a list, got {type(test_files)!r}")

    for tf in test_files:
        if not isinstance(tf, str):
            raise TypeError(f"Each test file must be a string, got {type(tf)!r}")

    return {feature_id: list(test_files)}


def get_feature_test_files(acceptance_criteria: list[str] | None) -> list[str]:
    """Return pytest test file paths declared in *acceptance_criteria*.

    Scans the acceptance criteria list for items whose prefix (case-insensitive)
    is ``"pytest:"`` and returns the trailing path token from each.  This is
    the canonical function for determining which test files a feature owns,
    based solely on its ``pytest:`` ACs.  A feature with no ``pytest:`` ACs
    owns no tests and MUST NOT be scapegoated for failures in others.

    Args:
        acceptance_criteria: List of AC strings, or ``None``.  When ``None``
            or empty, returns an empty list without raising.

    Returns:
        List of path strings (e.g. ``["tests/test_foo.py"]``), in the order
        they appear in *acceptance_criteria*.  Empty when no ``pytest:`` ACs
        are present.
    """
    if acceptance_criteria is None:
        return []

    result: list[str] = []
    for ac in _parse_ac_list(acceptance_criteria):
        m = _PYTEST_AC_RE.match(ac)
        if m:
            result.append(m.group(1).strip())
    return result
