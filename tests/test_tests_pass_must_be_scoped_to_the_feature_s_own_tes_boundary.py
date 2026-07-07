"""Boundary cases for tests_pass feature scoping.

Empty, zero, or minimum input returns a well-defined result rather than
raising: a feature with no ``pytest:`` ACs and no ``tests/<feature_id>/``
subtree yields an empty list (meaning "no tests to run"), never a fallback to
the whole tree.
"""

from __future__ import annotations

from pathlib import Path

from bob.verification.per_feature_test_scope import (
    build_scoped_pytest_argv,
    collect_feature_test_paths,
    scope_pytest_to_feature,
)

FEATURE_ID = "5a2360d6-1d50-45bd-acf5-2e6090937b7c"


def test_empty_acs_no_subtree_returns_empty_list(tmp_path: Path) -> None:
    result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
    assert result == []


def test_empty_acs_returns_empty_set(tmp_path: Path) -> None:
    result = collect_feature_test_paths(FEATURE_ID, [], tmp_path)
    assert result == set()


def test_acs_with_no_pytest_prefix_returns_empty(tmp_path: Path) -> None:
    acs = ["File exists: src/x.py", "Function defined: mod.fn", "integration: mod"]
    assert scope_pytest_to_feature(FEATURE_ID, acs, tmp_path) == []


def test_build_argv_empty_when_no_paths(tmp_path: Path) -> None:
    argv = build_scoped_pytest_argv(FEATURE_ID, [], tmp_path)
    assert argv == []


def test_empty_pytest_expr_is_ignored(tmp_path: Path) -> None:
    # A malformed but string AC whose path portion is empty must not crash and
    # must not add a bare path.
    acs = ["pytest:", "pytest:   "]
    assert scope_pytest_to_feature(FEATURE_ID, acs, tmp_path) == []


def test_result_is_sorted(tmp_path: Path) -> None:
    acs = ["pytest: tests/test_z.py", "pytest: tests/test_a.py"]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert result == sorted(result)
    assert result == ["tests/test_a.py", "tests/test_z.py"]
