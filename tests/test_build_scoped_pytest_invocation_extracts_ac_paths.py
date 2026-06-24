"""Tests that build_scoped_pytest_invocation correctly extracts pytest: AC paths.

Feature: 9901139e-bde3-4f3d-b648-f83d2494f98d
AC: pytest: tests/test_build_scoped_pytest_invocation_extracts_ac_paths.py
"""

from __future__ import annotations

from bob3.superpowers import build_scoped_pytest_invocation


class TestBuildScopedPytestInvocationExtractsAcPaths:
    def test_single_pytest_ac_extracts_path(self):
        acs = ["pytest: tests/test_foo.py"]
        result = build_scoped_pytest_invocation(acs)
        assert result == "python -m pytest tests/test_foo.py -v"

    def test_multiple_pytest_acs_joins_paths(self):
        acs = ["pytest: tests/test_a.py", "pytest: tests/test_b.py"]
        result = build_scoped_pytest_invocation(acs)
        assert "tests/test_a.py" in result
        assert "tests/test_b.py" in result
        assert result.startswith("python -m pytest ")
        assert result.endswith(" -v")

    def test_non_pytest_acs_are_ignored(self):
        acs = [
            "Function defined: bob3.superpowers.foo",
            "integration: bob3.bar",
            "pytest: tests/test_real.py",
        ]
        result = build_scoped_pytest_invocation(acs)
        assert result == "python -m pytest tests/test_real.py -v"
        assert "Function defined" not in result
        assert "integration" not in result

    def test_pytest_prefix_case_insensitive(self):
        acs = ["Pytest: tests/test_ci.py"]
        result = build_scoped_pytest_invocation(acs)
        assert "tests/test_ci.py" in result

    def test_paths_with_subdirectories_preserved(self):
        acs = ["pytest: tests/myfeature/test_specific.py"]
        result = build_scoped_pytest_invocation(acs)
        assert "tests/myfeature/test_specific.py" in result

    def test_invocation_includes_verbose_flag(self):
        acs = ["pytest: tests/test_x.py"]
        result = build_scoped_pytest_invocation(acs)
        assert " -v" in result

    def test_invocation_is_runnable_python_module_call(self):
        acs = ["pytest: tests/test_x.py"]
        result = build_scoped_pytest_invocation(acs)
        assert result.startswith("python -m pytest ")
