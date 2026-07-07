"""Error paths for tests_pass feature scoping.

Invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest

from bob.verification.per_feature_test_scope import (
    SiblingTestCollectionError,
    collect_feature_test_paths,
    scope_pytest_to_feature,
)

FEATURE_ID = "5a2360d6-1d50-45bd-acf5-2e6090937b7c"
SIBLING_ID = "deadbeef-1111-2222-3333-444455556666"


@pytest.mark.parametrize("bad", [None, "", "   ", 123, ["not-a-str"]])
def test_invalid_feature_id_raises_value_error(bad, tmp_path) -> None:
    with pytest.raises(ValueError):
        scope_pytest_to_feature(bad, [], tmp_path)


def test_acs_not_a_list_raises_value_error(tmp_path) -> None:
    with pytest.raises(ValueError):
        scope_pytest_to_feature(FEATURE_ID, "pytest: tests/x.py", tmp_path)


def test_acs_containing_non_string_raises_value_error(tmp_path) -> None:
    with pytest.raises(ValueError):
        scope_pytest_to_feature(FEATURE_ID, ["pytest: tests/x.py", 42], tmp_path)


@pytest.mark.parametrize("bad_ws", [None, "", "   "])
def test_invalid_workspace_raises_value_error(bad_ws) -> None:
    with pytest.raises(ValueError):
        scope_pytest_to_feature(FEATURE_ID, [], bad_ws)


def test_workspace_wrong_type_raises_value_error() -> None:
    with pytest.raises(ValueError):
        scope_pytest_to_feature(FEATURE_ID, [], 12345)


def test_collect_paths_also_validates(tmp_path) -> None:
    with pytest.raises(ValueError):
        collect_feature_test_paths("", [], tmp_path)


def test_sibling_subtree_ac_raises(tmp_path) -> None:
    """A pytest: AC referencing a sibling subtree must raise, not silently pass."""
    acs = [f"pytest: tests/{SIBLING_ID}/test_fail.py"]
    with pytest.raises(SiblingTestCollectionError):
        scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
