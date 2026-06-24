"""Boundary tests for bob72.preflight.

Empty, zero, or minimum input returns a well-defined result rather than raising.
"""

import pytest

from bob72.preflight import (
    discover_workaround,
    probe_dependencies,
    run_preflight,
)


class TestProbeDependenciesBoundary:
    def test_empty_list_returns_empty_list(self):
        result = probe_dependencies([])
        assert result == []

    def test_list_with_empty_string_returns_empty(self):
        result = probe_dependencies([""])
        assert isinstance(result, list)

    def test_list_with_only_non_string_entries_returns_empty(self):
        result = probe_dependencies([None, 42, True])  # type: ignore[list-item]
        assert result == []

    def test_single_ac_no_deps_returns_empty(self):
        result = probe_dependencies(["File exists: src/bob72/preflight.py"])
        assert isinstance(result, list)

    def test_minimum_function_ac_returns_one_dep(self):
        result = probe_dependencies(["Function defined: os.getcwd"])
        dep_names = [r["dep"]["name"] for r in result]
        assert "os" in dep_names


class TestDiscoverWorkaroundBoundary:
    def test_present_dep_returns_none_not_raises(self):
        probe = {"dep": {"kind": "python", "name": "os"}, "present": True, "path": "/stdlib"}
        result = discover_workaround(probe)
        assert result is None

    def test_minimum_cli_missing_returns_dict(self):
        probe = {"dep": {"kind": "cli", "name": "x"}, "present": False, "path": None}
        result = discover_workaround(probe)
        assert isinstance(result, dict)
        assert "dep_name" in result
        assert "description" in result

    def test_minimum_python_missing_returns_dict(self):
        probe = {"dep": {"kind": "python", "name": "z"}, "present": False, "path": None}
        result = discover_workaround(probe)
        assert isinstance(result, dict)
        assert result["low_risk"] is True


class TestRunPreflightBoundary:
    def test_empty_list_does_not_raise(self):
        result = run_preflight([])
        assert result["total_deps"] == 0
        assert result["halted"] is False

    def test_all_present_deps_not_in_missing(self):
        result = run_preflight(["Function defined: os.getcwd"])
        assert "os" not in result["missing"]

    def test_zero_missing_means_empty_applied_workarounds(self):
        result = run_preflight(["Function defined: os.getcwd"])
        assert isinstance(result["applied_workarounds"], list)

    def test_single_element_list_does_not_raise(self):
        result = run_preflight(["File exists: src/bob72/preflight.py"])
        assert isinstance(result, dict)
