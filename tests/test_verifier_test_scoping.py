"""Tests for bob.verifier_test_scoping — AC-named per-feature pytest scoping.

AC: pytest: tests/test_verifier_test_scoping.py
File exists: src/bob/verifier_test_scoping.py
Function defined: bob.verifier_test_scoping.scope_pytest_to_feature
integration: bob.verifier
"""

from __future__ import annotations

import pytest

from bob.verifier_test_scoping import (
    SiblingTestCollectionError,
    assert_no_sibling_collection,
    collect_feature_test_paths,
    scope_pytest_to_feature,
)

FEATURE_ID = "c767990c-3fed-4f35-aa3d-943e0d473750"
OTHER_FEATURE_ID = "11111111-2222-3333-4444-555555555555"


def test_scope_pytest_to_feature_is_defined():
    """Function defined AC: the symbol exists and is callable."""
    assert callable(scope_pytest_to_feature)


def test_pytest_ac_paths_are_returned(tmp_path):
    """pytest: AC entries yield their path portion."""
    acs = [
        "pytest: tests/test_verifier_test_scoping.py",
        "File exists: src/bob/verifier_test_scoping.py",
        "integration: bob.verifier",
    ]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert result == ["tests/test_verifier_test_scoping.py"]


def test_node_id_suffix_is_stripped(tmp_path):
    """A pytest: AC with a ::node-id keeps only the file path."""
    acs = ["pytest: tests/test_foo.py::TestClass::test_method"]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert result == ["tests/test_foo.py"]


def test_feature_subtree_included_when_present(tmp_path):
    """tests/<feature_id>/ is included when the directory exists."""
    (tmp_path / "tests" / FEATURE_ID).mkdir(parents=True)
    acs = ["pytest: tests/test_a.py"]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert "tests/test_a.py" in result
    assert f"tests/{FEATURE_ID}" in result


def test_bare_tests_never_returned(tmp_path):
    """The scoped result never contains a bare tests/ path."""
    acs = ["pytest: tests/test_a.py"]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert "tests" not in result
    assert "tests/" not in result


def test_empty_acs_returns_empty(tmp_path):
    """No pytest: ACs and no subtree returns []."""
    assert scope_pytest_to_feature(FEATURE_ID, [], tmp_path) == []


def test_sibling_subtree_ac_raises(tmp_path):
    """A pytest: AC referencing another feature's subtree raises."""
    acs = [f"pytest: tests/{OTHER_FEATURE_ID}/test_bad.py"]
    with pytest.raises(SiblingTestCollectionError):
        scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)


def test_collect_feature_test_paths_returns_set(tmp_path):
    """collect_feature_test_paths returns a set of paths."""
    acs = ["pytest: tests/test_x.py"]
    result = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
    assert isinstance(result, set)
    assert result == {"tests/test_x.py"}


def test_assert_no_sibling_collection_rejects_bare_tests(tmp_path):
    """assert_no_sibling_collection rejects bare tests/ argv."""
    with pytest.raises(SiblingTestCollectionError):
        assert_no_sibling_collection(FEATURE_ID, ["tests/"], tmp_path)


def test_resolves_to_same_impl_as_verifier():
    """integration: bob.verifier — same underlying implementation."""
    from bob import verifier

    assert verifier.SiblingTestCollectionError is SiblingTestCollectionError
