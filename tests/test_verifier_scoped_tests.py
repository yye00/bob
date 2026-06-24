"""Tests for bob.verifier_scoped_tests.scope_pytest_to_feature.

AC: pytest: tests/test_verifier_scoped_tests.py

Verifies that scope_pytest_to_feature returns only the current feature's
test paths, never the full test suite or sibling feature subtrees.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob.verifier_scoped_tests import SiblingTestCollectionError, scope_pytest_to_feature

FEATURE_ID = "06cb1af5-0a51-415b-a487-a0dd5a9d61f7"
SIBLING_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class TestScopePytestToFeature:
    def test_returns_list(self, tmp_path):
        result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
        assert isinstance(result, list)

    def test_empty_acs_no_subtree_returns_empty(self, tmp_path):
        result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
        assert result == []

    def test_pytest_ac_included_in_result(self, tmp_path):
        acs = ["pytest: tests/test_foo.py"]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert "tests/test_foo.py" in result

    def test_multiple_pytest_acs_all_included(self, tmp_path):
        acs = [
            "pytest: tests/test_alpha.py",
            "pytest: tests/test_beta.py",
            "File exists: src/bob/module.py",
        ]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert "tests/test_alpha.py" in result
        assert "tests/test_beta.py" in result

    def test_non_pytest_acs_not_added(self, tmp_path):
        acs = [
            "File exists: src/bob/foo.py",
            "Function defined: bob.foo.bar",
            "integration: bob.foo",
        ]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert result == []

    def test_result_is_sorted(self, tmp_path):
        acs = [
            "pytest: tests/test_z.py",
            "pytest: tests/test_a.py",
            "pytest: tests/test_m.py",
        ]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert result == sorted(result)

    def test_feature_subtree_included_when_exists(self, tmp_path):
        feature_dir = tmp_path / "tests" / FEATURE_ID
        feature_dir.mkdir(parents=True)
        result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
        assert f"tests/{FEATURE_ID}" in result

    def test_sibling_uuid_in_pytest_ac_raises(self, tmp_path):
        acs = [f"pytest: tests/{SIBLING_ID}/test_sibling.py"]
        with pytest.raises(SiblingTestCollectionError):
            scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)

    def test_node_id_suffix_stripped(self, tmp_path):
        acs = ["pytest: tests/test_foo.py::TestClass::test_method"]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert "tests/test_foo.py" in result
        assert any("::" not in p for p in result)

    def test_sibling_collection_error_is_runtime_error(self, tmp_path):
        acs = [f"pytest: tests/{SIBLING_ID}/test_other.py"]
        with pytest.raises(RuntimeError):
            scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)

    def test_no_duplicate_paths(self, tmp_path):
        acs = [
            "pytest: tests/test_dup.py",
            "pytest: tests/test_dup.py",
        ]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert len(result) == len(set(result))


class TestOrchestratorIntegration:
    def test_orchestrator_exposes_scope_pytest_to_feature(self):
        from bob.orchestrator import scope_pytest_to_feature as orch_fn
        assert callable(orch_fn)

    def test_orchestrator_exposes_sibling_error(self):
        from bob.orchestrator import SiblingTestCollectionError as ErrCls
        assert issubclass(ErrCls, RuntimeError)
