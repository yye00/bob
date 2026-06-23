"""Error-path tests for bob3.verifier.scope_pytest_to_feature.

AC: pytest: tests/test_verifier_must_scope_pytest_to_the_current_feature__error.py
    — invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest

from bob3.verifier import (
    SiblingTestCollectionError,
    scope_pytest_to_feature,
    assert_no_sibling_collection,
)

FEATURE_ID = "22ea12cd-52a7-4f0b-8d70-4d63bdae9514"
OTHER_FEATURE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_sibling_uuid_in_pytest_ac_raises(tmp_path):
    """A pytest: AC referencing another feature's UUID path raises SiblingTestCollectionError."""
    acs = [f"pytest: tests/{OTHER_FEATURE_ID}/test_sibling.py"]
    with pytest.raises(SiblingTestCollectionError):
        scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)


def test_bare_tests_path_in_argv_raises(tmp_path):
    """assert_no_sibling_collection raises SiblingTestCollectionError for bare tests/."""
    with pytest.raises(SiblingTestCollectionError):
        assert_no_sibling_collection(FEATURE_ID, ["tests"], tmp_path)


def test_bare_tests_slash_in_argv_raises(tmp_path):
    """assert_no_sibling_collection raises SiblingTestCollectionError for 'tests/'."""
    with pytest.raises(SiblingTestCollectionError):
        assert_no_sibling_collection(FEATURE_ID, ["tests/"], tmp_path)


def test_other_uuid_in_argv_raises(tmp_path):
    """assert_no_sibling_collection raises for a sibling UUID subtree in argv."""
    with pytest.raises(SiblingTestCollectionError):
        assert_no_sibling_collection(FEATURE_ID, [f"tests/{OTHER_FEATURE_ID}"], tmp_path)


def test_scope_does_not_silently_succeed_on_sibling(tmp_path):
    """scope_pytest_to_feature must raise, not silently return sibling paths."""
    acs = [f"pytest: tests/{OTHER_FEATURE_ID}/test_bad.py"]
    try:
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        # If it didn't raise, the sibling must not appear in the result
        assert f"tests/{OTHER_FEATURE_ID}" not in result, (
            "scope_pytest_to_feature silently returned sibling path — must raise"
        )
    except SiblingTestCollectionError:
        pass  # expected


def test_sibling_collection_error_is_not_suppressed(tmp_path):
    """SiblingTestCollectionError is a RuntimeError subclass, not suppressed by broad except."""
    acs = [f"pytest: tests/{OTHER_FEATURE_ID}/test_other.py"]
    with pytest.raises((SiblingTestCollectionError, RuntimeError)):
        scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)


def test_assert_no_sibling_collection_raises_on_dotslash_bare_tests(tmp_path):
    """./tests (normalised to 'tests') raises SiblingTestCollectionError."""
    with pytest.raises(SiblingTestCollectionError):
        assert_no_sibling_collection(FEATURE_ID, ["./tests"], tmp_path)


def test_assert_no_sibling_collection_raises_on_other_uuid_with_dotslash(tmp_path):
    """./tests/<other_uuid> (normalised) raises SiblingTestCollectionError."""
    with pytest.raises(SiblingTestCollectionError):
        assert_no_sibling_collection(FEATURE_ID, [f"./tests/{OTHER_FEATURE_ID}"], tmp_path)
