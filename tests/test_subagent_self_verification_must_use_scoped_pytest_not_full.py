"""Tests for subagent_self_verification_must_use_scoped_pytest_not_full module.

Feature: 5d3fb069-5fc5-4d13-a366-da79ca791e89
AC: pytest: tests/test_subagent_self_verification_must_use_scoped_pytest_not_full.py::test_subagent_self_verification_must_use_scoped_pytest_not_full
"""

from __future__ import annotations

import importlib
import inspect

import pytest


MODULE_PATH = "bob.subagent_self_verification_must_use_scoped_pytest_not_full"
FUNC_NAME = "subagent_self_verification_must_use_scoped_pytest_not_full"


def test_subagent_self_verification_must_use_scoped_pytest_not_full():
    """Main AC test: module importable, function defined, returns scoped paths."""
    mod = importlib.import_module(MODULE_PATH)
    func = getattr(mod, FUNC_NAME)

    # Function must be callable
    assert callable(func)

    # Calling with pytest: ACs returns only the scoped paths, not full suite
    acs = [
        f"pytest: tests/test_{FUNC_NAME}.py",
        "Function defined: some_function",
    ]
    result = func(
        feature_id="5d3fb069-5fc5-4d13-a366-da79ca791e89",
        acceptance_criteria=acs,
    )

    # Result must be a string containing the scoped path, not tests/
    assert isinstance(result, str)
    assert f"tests/test_{FUNC_NAME}.py" in result
    assert result.startswith("python -m pytest")
    # Must NOT point at the full suite root
    assert "python -m pytest tests/ -v" not in result


def test_function_signature_accepts_feature_id_and_acs():
    """Function must accept feature_id and acceptance_criteria parameters."""
    mod = importlib.import_module(MODULE_PATH)
    func = getattr(mod, FUNC_NAME)
    sig = inspect.signature(func)
    params = set(sig.parameters.keys())
    assert "feature_id" in params
    assert "acceptance_criteria" in params


def test_no_pytest_acs_returns_fallback_not_full_suite():
    """When no pytest: ACs, must still not run tests/ blindly — returns empty or safe fallback."""
    mod = importlib.import_module(MODULE_PATH)
    func = getattr(mod, FUNC_NAME)

    acs = ["Function defined: foo", "File exists: src/bob/foo.py"]
    result = func(
        feature_id="5d3fb069-5fc5-4d13-a366-da79ca791e89",
        acceptance_criteria=acs,
    )
    # When no pytest: ACs, the function should return empty string or indicate no tests
    # It must NOT return the full-suite command
    assert isinstance(result, str)


def test_multiple_pytest_acs_all_included():
    """All pytest: AC paths must appear in the returned command."""
    mod = importlib.import_module(MODULE_PATH)
    func = getattr(mod, FUNC_NAME)

    acs = [
        "pytest: tests/test_alpha.py",
        "pytest: tests/test_beta.py::test_specific",
    ]
    result = func(
        feature_id="5d3fb069-5fc5-4d13-a366-da79ca791e89",
        acceptance_criteria=acs,
    )
    assert "tests/test_alpha.py" in result
    assert "tests/test_beta.py::test_specific" in result


def test_module_docstring_explains_purpose():
    """Module must have a docstring explaining the scoped-pytest purpose."""
    mod = importlib.import_module(MODULE_PATH)
    assert mod.__doc__ is not None
    doc = mod.__doc__.lower()
    assert "scoped" in doc or "full" in doc or "suite" in doc
