"""Boundary tests for build_scoped_pytest_invocation when no pytest: ACs are present.

Feature: 9901139e-bde3-4f3d-b648-f83d2494f98d
AC: pytest: tests/test_build_scoped_pytest_invocation_boundary_no_pytest_acs.py
"""

from __future__ import annotations

from bob.superpowers import build_scoped_pytest_invocation


FULL_SUITE_FALLBACK = "python -m pytest tests/ -v"


class TestBuildScopedPytestInvocationBoundaryNoPytestAcs:
    def test_none_returns_full_suite_fallback(self):
        result = build_scoped_pytest_invocation(None)
        assert result == FULL_SUITE_FALLBACK

    def test_empty_list_returns_full_suite_fallback(self):
        result = build_scoped_pytest_invocation([])
        assert result == FULL_SUITE_FALLBACK

    def test_no_pytest_acs_returns_full_suite_fallback(self):
        acs = ["Function defined: foo", "integration: bar", "File exists: src/x.py"]
        result = build_scoped_pytest_invocation(acs)
        assert result == FULL_SUITE_FALLBACK

    def test_pytest_ac_with_empty_path_ignored(self):
        acs = ["pytest:", "pytest:   ", "Function defined: foo"]
        result = build_scoped_pytest_invocation(acs)
        assert result == FULL_SUITE_FALLBACK

    def test_return_type_is_str(self):
        assert isinstance(build_scoped_pytest_invocation(None), str)
        assert isinstance(build_scoped_pytest_invocation([]), str)
        assert isinstance(build_scoped_pytest_invocation(["Function defined: x"]), str)

    def test_fallback_is_valid_pytest_invocation(self):
        result = build_scoped_pytest_invocation(None)
        assert "python -m pytest" in result
        assert "tests/" in result
