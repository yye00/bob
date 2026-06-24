"""Tests for bob73.environment_capability module."""

import pytest

from bob73.environment_capability import (
    MissingDependencyError,
    apply_workaround,
    probe_dependencies,
    run_preflight,
)


class TestProbeDependencies:
    def test_empty_list_returns_empty(self):
        result = probe_dependencies([])
        assert result == []

    def test_invalid_input_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            probe_dependencies(None)  # type: ignore[arg-type]

    def test_string_input_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            probe_dependencies("not a list")  # type: ignore[arg-type]

    def test_function_defined_ac_produces_python_probe(self):
        results = probe_dependencies(["Function defined: os.path"])
        dep_names = [r["dep"]["name"] for r in results]
        assert "os" in dep_names

    def test_os_module_is_present(self):
        results = probe_dependencies(["Function defined: os.getcwd"])
        os_probes = [r for r in results if r["dep"]["name"] == "os"]
        assert os_probes, "Expected probe for 'os'"
        assert os_probes[0]["present"] is True

    def test_pytest_prefix_ac_produces_cli_probe(self):
        results = probe_dependencies(["pytest: tests/test_something.py"])
        cli_names = [r["dep"]["name"] for r in results if r["dep"]["kind"] == "cli"]
        assert "pytest" in cli_names

    def test_command_ac_produces_cli_probe(self):
        results = probe_dependencies(["command: git --version"])
        cli_names = [r["dep"]["name"] for r in results if r["dep"]["kind"] == "cli"]
        assert "git" in cli_names

    def test_nonexistent_module_not_present(self):
        results = probe_dependencies(["Function defined: absent_module_xyz987.foo"])
        absent = [r for r in results if r["dep"]["name"] == "absent_module_xyz987"]
        assert absent, "Expected probe for absent module"
        assert absent[0]["present"] is False

    def test_nonexistent_cli_not_present(self):
        results = probe_dependencies(["command: __totally_absent_cli_xyz987__"])
        absent = [r for r in results if r["dep"]["name"] == "__totally_absent_cli_xyz987__"]
        assert absent, "Expected probe for absent CLI"
        assert absent[0]["present"] is False

    def test_returns_list_of_dicts_with_expected_keys(self):
        results = probe_dependencies(["Function defined: os.getcwd"])
        assert isinstance(results, list)
        for r in results:
            assert "dep" in r
            assert "present" in r
            assert "path" in r


class TestApplyWorkaround:
    def test_present_dep_returns_none(self):
        probe = {"dep": {"kind": "python", "name": "os"}, "present": True, "path": "/stdlib"}
        result = apply_workaround(probe)
        assert result is None

    def test_missing_python_dep_returns_dict(self):
        probe = {"dep": {"kind": "python", "name": "__absent_mod__"}, "present": False, "path": None}
        result = apply_workaround(probe)
        assert isinstance(result, dict)
        assert result["dep_name"] == "__absent_mod__"
        assert result["low_risk"] is True

    def test_missing_cli_dep_returns_dict(self):
        probe = {"dep": {"kind": "cli", "name": "__absent_cli__"}, "present": False, "path": None}
        result = apply_workaround(probe)
        assert isinstance(result, dict)
        assert result["dep_name"] == "__absent_cli__"
        assert result["low_risk"] is False

    def test_none_input_raises_value_error(self):
        with pytest.raises(ValueError, match="probe_result must be a dict"):
            apply_workaround(None)  # type: ignore[arg-type]

    def test_missing_keys_raises_value_error(self):
        with pytest.raises(ValueError, match="must have 'dep' and 'present' keys"):
            apply_workaround({"dep": {"kind": "cli", "name": "git"}})

    def test_result_has_required_keys(self):
        probe = {"dep": {"kind": "python", "name": "yaml"}, "present": False, "path": None}
        result = apply_workaround(probe)
        assert result is not None
        for key in ("dep_name", "description", "low_risk", "commands"):
            assert key in result


class TestRunPreflight:
    def test_empty_list_does_not_raise(self):
        result = run_preflight([])
        assert result["total_deps"] == 0
        assert result["halted"] is False

    def test_stdlib_module_not_in_missing(self):
        result = run_preflight(["Function defined: os.getcwd"])
        assert "os" not in result["missing"]

    def test_invalid_input_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            run_preflight(None)  # type: ignore[arg-type]

    def test_high_risk_missing_dep_raises_missing_dependency_error(self):
        ac = "command: __nonexistent_cli_guaranteed_absent_xyz987__"
        with pytest.raises(MissingDependencyError):
            run_preflight([ac])

    def test_missing_dep_error_is_value_error_subclass(self):
        ac = "command: __nonexistent_cli_guaranteed_absent_xyz987__"
        with pytest.raises(ValueError):
            run_preflight([ac])

    def test_result_has_expected_keys(self):
        result = run_preflight(["Function defined: os.getcwd"])
        for key in ("total_deps", "missing", "applied_workarounds", "halted"):
            assert key in result

    def test_applied_workarounds_is_list(self):
        result = run_preflight(["Function defined: os.getcwd"])
        assert isinstance(result["applied_workarounds"], list)
