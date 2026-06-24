"""Tests for bob72.preflight module.

Verifies probe_dependencies and discover_workaround, plus the run_preflight
integration pipeline.
"""

import pytest

from bob72.preflight import (
    MissingDependencyError,
    discover_workaround,
    probe_dependencies,
    run_preflight,
)


# ---------------------------------------------------------------------------
# probe_dependencies
# ---------------------------------------------------------------------------


class TestProbeDependencies:
    def test_empty_list_returns_empty(self):
        result = probe_dependencies([])
        assert result == []

    def test_invalid_input_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            probe_dependencies(None)  # type: ignore[arg-type]

    def test_invalid_string_input_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            probe_dependencies("not a list")  # type: ignore[arg-type]

    def test_present_python_module_is_detected(self):
        results = probe_dependencies(["Function defined: os.getcwd"])
        os_results = [r for r in results if r["dep"]["name"] == "os"]
        assert os_results, "expected 'os' dep to appear in probe results"
        assert os_results[0]["present"] is True

    def test_missing_python_module_detected_absent(self):
        results = probe_dependencies(["Function defined: nonexistent_xyz_abc_987_module.func"])
        nonexistent = [r for r in results if r["dep"]["name"] == "nonexistent_xyz_abc_987_module"]
        assert nonexistent, "expected the nonexistent module to appear"
        assert nonexistent[0]["present"] is False
        assert nonexistent[0]["path"] is None

    def test_present_cli_tool_detected(self):
        results = probe_dependencies(["command: python3 --version"])
        python_results = [r for r in results if r["dep"]["name"] == "python3"]
        assert python_results, "expected 'python3' dep to appear"
        assert python_results[0]["present"] is True
        assert python_results[0]["path"] is not None

    def test_missing_cli_tool_detected_absent(self):
        results = probe_dependencies(["command: __nonexistent_cli_tool_xyz_987__"])
        missing = [r for r in results if r["dep"]["name"] == "__nonexistent_cli_tool_xyz_987__"]
        assert missing, "expected the nonexistent CLI tool to appear"
        assert missing[0]["present"] is False

    def test_each_result_has_required_keys(self):
        results = probe_dependencies(["Function defined: json.loads"])
        for r in results:
            assert "dep" in r
            assert "present" in r
            assert "path" in r
            assert isinstance(r["present"], bool)

    def test_non_string_elements_skipped(self):
        results = probe_dependencies(["Function defined: os.getcwd", None, 42])  # type: ignore[list-item]
        assert isinstance(results, list)

    def test_pytest_ac_produces_cli_probe(self):
        results = probe_dependencies(["pytest: tests/test_something.py"])
        pytest_results = [r for r in results if r["dep"]["name"] == "pytest"]
        assert pytest_results, "pytest AC should produce a CLI probe for 'pytest'"


# ---------------------------------------------------------------------------
# discover_workaround
# ---------------------------------------------------------------------------


class TestDiscoverWorkaround:
    def test_invalid_input_raises_value_error(self):
        with pytest.raises(ValueError, match="probe_result must be a dict"):
            discover_workaround("not a dict")  # type: ignore[arg-type]

    def test_missing_keys_raises_value_error(self):
        with pytest.raises(ValueError, match="must have 'dep' and 'present' keys"):
            discover_workaround({"dep": {"kind": "python", "name": "foo"}})

    def test_present_dep_returns_none(self):
        probe = {"dep": {"kind": "python", "name": "os"}, "present": True, "path": "/stdlib"}
        assert discover_workaround(probe) is None

    def test_missing_python_dep_returns_workaround(self):
        probe = {"dep": {"kind": "python", "name": "__unknown_mod__"}, "present": False, "path": None}
        result = discover_workaround(probe)
        assert result is not None
        assert result["dep_name"] == "__unknown_mod__"
        assert isinstance(result["description"], str) and result["description"]
        assert isinstance(result["commands"], list)
        assert "low_risk" in result

    def test_missing_python_dep_is_low_risk(self):
        probe = {"dep": {"kind": "python", "name": "someunknownpkg"}, "present": False, "path": None}
        result = discover_workaround(probe)
        assert result is not None
        assert result["low_risk"] is True

    def test_missing_cli_dep_returns_workaround(self):
        probe = {"dep": {"kind": "cli", "name": "__nonexistent_cli__"}, "present": False, "path": None}
        result = discover_workaround(probe)
        assert result is not None
        assert result["dep_name"] == "__nonexistent_cli__"
        assert isinstance(result["description"], str)

    def test_missing_cli_dep_is_high_risk(self):
        probe = {"dep": {"kind": "cli", "name": "__nonexistent_cli__"}, "present": False, "path": None}
        result = discover_workaround(probe)
        assert result is not None
        assert result["low_risk"] is False

    def test_known_dep_git_returns_specific_workaround(self):
        probe = {"dep": {"kind": "cli", "name": "git"}, "present": False, "path": None}
        result = discover_workaround(probe)
        assert result is not None
        assert result["dep_name"] == "git"
        assert "git" in result["description"].lower()

    def test_known_dep_yaml_is_low_risk(self):
        probe = {"dep": {"kind": "python", "name": "yaml"}, "present": False, "path": None}
        result = discover_workaround(probe)
        assert result is not None
        assert result["low_risk"] is True


# ---------------------------------------------------------------------------
# run_preflight (integration pipeline)
# ---------------------------------------------------------------------------


class TestRunPreflight:
    def test_empty_ac_list_returns_zero_total(self):
        result = run_preflight([])
        assert result["total_deps"] == 0
        assert result["missing"] == []
        assert result["applied_workarounds"] == []
        assert result["halted"] is False

    def test_invalid_input_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            run_preflight(None)  # type: ignore[arg-type]

    def test_present_python_dep_not_in_missing(self):
        result = run_preflight(["Function defined: os.getcwd"])
        assert "os" not in result["missing"]

    def test_missing_high_risk_cli_raises_error(self):
        ac = "command: __absolutely_nonexistent_cli_tool_xyz_987__"
        with pytest.raises(MissingDependencyError, match="__absolutely_nonexistent_cli_tool_xyz_987__"):
            run_preflight([ac])

    def test_result_dict_has_expected_keys(self):
        result = run_preflight(["Function defined: json.loads"])
        assert "total_deps" in result
        assert "missing" in result
        assert "applied_workarounds" in result
        assert "halted" in result

    def test_halted_is_false_on_success(self):
        result = run_preflight([])
        assert result["halted"] is False

    def test_error_message_contains_dep_name(self):
        ac = "command: __guaranteed_missing_cli_xyz_abc__"
        with pytest.raises(MissingDependencyError) as exc_info:
            run_preflight([ac])
        assert "__guaranteed_missing_cli_xyz_abc__" in str(exc_info.value)

    def test_missing_python_dep_auto_applied(self):
        ac = "Function defined: nonexistent_xyz_module_abc987.some_func"
        result = run_preflight([ac])
        dep_name = "nonexistent_xyz_module_abc987"
        assert dep_name in result["missing"] or dep_name in result["applied_workarounds"]
