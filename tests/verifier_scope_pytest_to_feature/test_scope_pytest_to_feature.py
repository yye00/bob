"""Tests for bob3.verifier.scope_pytest_to_feature_subtree and related API.

Covers the ACs for feature 6e7756d5-1329-4e2a-981e-4cd77703635a:
- Function defined: bob3.verifier.scope_pytest_to_feature_subtree
- File exists: src/bob3/verifier.py
- integration: bob3.verifier
- behavior: handles empty/zero input (boundary case)
- behavior: raises ValueError or rejection on invalid input
- File exists: test_ac_13_integration_bob3_orchestrator_run_loop.py
- File exists: test_cli_spec_trace_command.py
"""

from __future__ import annotations

import pathlib
import tempfile
from pathlib import Path

import pytest

from bob3.verifier import (
    SiblingTestCollectionError,
    scope_pytest_to_feature,
    scope_pytest_to_feature_subtree,
)

FEATURE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SIBLING_ID = "11111111-2222-3333-4444-555555555555"

WORKSPACE = pathlib.Path(__file__).parent.parent.parent


class TestFunctionDefined:
    """Function defined: bob3.verifier.scope_pytest_to_feature_subtree"""

    def test_function_is_callable(self):
        assert callable(scope_pytest_to_feature_subtree)

    def test_function_is_importable_from_bob3_verifier(self):
        import bob3.verifier as m
        assert hasattr(m, "scope_pytest_to_feature_subtree")
        assert callable(m.scope_pytest_to_feature_subtree)

    def test_alias_is_same_as_scope_pytest_to_feature(self):
        assert scope_pytest_to_feature_subtree is scope_pytest_to_feature


class TestVerifierPyExists:
    """File exists: src/bob3/verifier.py"""

    def test_src_bob3_verifier_py_exists(self):
        verifier_py = WORKSPACE / "src" / "bob3" / "verifier.py"
        assert verifier_py.exists(), f"Expected {verifier_py} to exist"


class TestIntegrationBob3Verifier:
    """integration: bob3.verifier"""

    def test_bob3_verifier_exposes_scope_pytest_to_feature_subtree(self):
        import bob3.verifier
        assert "scope_pytest_to_feature_subtree" in dir(bob3.verifier)

    def test_scope_pytest_to_feature_subtree_returns_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scope_pytest_to_feature_subtree(FEATURE_ID, [], tmp)
        assert isinstance(result, list)

    def test_scope_pytest_to_feature_subtree_with_pytest_ac(self):
        with tempfile.TemporaryDirectory() as tmp:
            acs = [f"pytest: tests/{FEATURE_ID}/test_foo.py"]
            result = scope_pytest_to_feature_subtree(FEATURE_ID, acs, tmp)
        assert f"tests/{FEATURE_ID}/test_foo.py" in result

    def test_scope_pytest_to_feature_subtree_with_feature_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            feature_dir = Path(tmp) / "tests" / FEATURE_ID
            feature_dir.mkdir(parents=True)
            result = scope_pytest_to_feature_subtree(FEATURE_ID, [], tmp)
        assert f"tests/{FEATURE_ID}" in result

    def test_scope_pytest_to_feature_subtree_result_is_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            acs = [
                f"pytest: tests/{FEATURE_ID}/test_z.py",
                f"pytest: tests/{FEATURE_ID}/test_a.py",
            ]
            result = scope_pytest_to_feature_subtree(FEATURE_ID, acs, tmp)
        assert result == sorted(result)

    def test_does_not_include_bare_tests_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scope_pytest_to_feature_subtree(FEATURE_ID, [], tmp)
        assert "tests" not in result
        assert "tests/" not in result


class TestBehaviorEmptyInput:
    """behavior: handles empty/zero input by returning well-defined result"""

    def test_empty_acs_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scope_pytest_to_feature_subtree(FEATURE_ID, [], tmp)
        assert result == []

    def test_none_like_empty_string_ac_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            acs = ["", "   ", "some non-pytest ac"]
            result = scope_pytest_to_feature_subtree(FEATURE_ID, acs, tmp)
        assert result == []

    def test_zero_pytest_acs_no_feature_dir_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scope_pytest_to_feature_subtree(FEATURE_ID, ["File exists: foo.py"], tmp)
        assert result == []

    def test_returns_list_not_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scope_pytest_to_feature_subtree(FEATURE_ID, [], tmp)
        assert result is not None


class TestBehaviorInvalidInput:
    """behavior: raises ValueError or rejection on invalid input, no silent success"""

    def test_sibling_pytest_ac_raises_sibling_collection_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            acs = [f"pytest: tests/{SIBLING_ID}/test_x.py"]
            with pytest.raises(SiblingTestCollectionError):
                scope_pytest_to_feature_subtree(FEATURE_ID, acs, tmp)

    def test_bare_tests_path_in_ac_raises_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            acs = ["pytest: tests/"]
            with pytest.raises(SiblingTestCollectionError):
                scope_pytest_to_feature_subtree(FEATURE_ID, acs, tmp)

    def test_bare_tests_without_slash_raises_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            acs = ["pytest: tests"]
            with pytest.raises(SiblingTestCollectionError):
                scope_pytest_to_feature_subtree(FEATURE_ID, acs, tmp)

    def test_sibling_collection_error_message_contains_sibling_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            acs = [f"pytest: tests/{SIBLING_ID}/test_x.py"]
            with pytest.raises(SiblingTestCollectionError, match=SIBLING_ID):
                scope_pytest_to_feature_subtree(FEATURE_ID, acs, tmp)


class TestFileExistsTestAc13:
    """File exists: test_ac_13_integration_bob3_orchestrator_run_loop.py"""

    def test_test_ac_13_integration_bob3_orchestrator_run_loop_exists(self):
        target = WORKSPACE / "tests" / "test_ac_13_integration_bob3_orchestrator_run_loop.py"
        assert target.exists(), f"Expected {target} to exist"
        assert target.is_file()
        assert target.name == "test_ac_13_integration_bob3_orchestrator_run_loop.py"


class TestFileExistsTestCliSpecTrace:
    """File exists: test_cli_spec_trace_command.py"""

    def test_test_cli_spec_trace_command_exists(self):
        target = WORKSPACE / "tests" / "test_cli_spec_trace_command.py"
        assert target.exists(), f"Expected {target} to exist"
        assert target.is_file()
        assert target.name == "test_cli_spec_trace_command.py"
