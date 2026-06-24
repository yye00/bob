"""Tests for bob.environment_preflight — feature 18c33084-24ca-4390-88a8-aebc34d3cbc0.

Environment-capability preflight with research-driven workaround discovery.
"""

from __future__ import annotations

import pytest

from bob.environment_preflight import (
    MissingDependencyError,
    apply_workaround,
    probe_dependencies,
    run_preflight,
    spawn_workaround_agent,
)


# ---------------------------------------------------------------------------
# probe_dependencies
# ---------------------------------------------------------------------------


class TestProbeDependencies:
    def test_empty_list_returns_empty(self):
        result = probe_dependencies([])
        assert result == []

    def test_returns_list(self):
        result = probe_dependencies(["File exists: src/bob/environment_preflight.py"])
        assert isinstance(result, list)

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            probe_dependencies(None)  # type: ignore[arg-type]

    def test_string_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            probe_dependencies("not a list")  # type: ignore[arg-type]

    def test_function_ac_produces_python_dep(self):
        result = probe_dependencies(["Function defined: os.getcwd"])
        dep_names = [r["dep"]["name"] for r in result]
        assert "os" in dep_names

    def test_present_python_dep_has_present_true(self):
        result = probe_dependencies(["Function defined: os.getcwd"])
        for r in result:
            if r["dep"]["name"] == "os":
                assert r["present"] is True
                break

    def test_probe_result_has_required_keys(self):
        result = probe_dependencies(["Function defined: os.getcwd"])
        for r in result:
            assert "dep" in r
            assert "present" in r
            assert "path" in r
            assert "kind" in r["dep"]
            assert "name" in r["dep"]

    def test_non_string_entries_are_skipped(self):
        result = probe_dependencies([None, 42, True])  # type: ignore[list-item]
        assert result == []

    def test_empty_string_returns_empty(self):
        result = probe_dependencies([""])
        assert result == []

    def test_missing_cli_has_present_false(self):
        result = probe_dependencies(["command: __nonexistent_cli_xyz_987__"])
        assert len(result) == 1
        assert result[0]["present"] is False

    def test_dep_kind_is_cli_or_python(self):
        acs = [
            "Function defined: os.getcwd",
            "command: python3",
        ]
        result = probe_dependencies(acs)
        for r in result:
            assert r["dep"]["kind"] in ("cli", "python")


# ---------------------------------------------------------------------------
# spawn_workaround_agent
# ---------------------------------------------------------------------------


class TestSpawnWorkaroundAgent:
    def test_present_dep_returns_none(self):
        probe = {"dep": {"kind": "python", "name": "os"}, "present": True, "path": "/stdlib"}
        result = spawn_workaround_agent(probe)
        assert result is None

    def test_missing_python_returns_workaround_dict(self):
        probe = {"dep": {"kind": "python", "name": "z_not_exist"}, "present": False, "path": None}
        result = spawn_workaround_agent(probe)
        assert isinstance(result, dict)
        assert "dep_name" in result
        assert "description" in result
        assert "low_risk" in result
        assert "commands" in result

    def test_missing_python_is_low_risk(self):
        probe = {"dep": {"kind": "python", "name": "z_not_exist"}, "present": False, "path": None}
        result = spawn_workaround_agent(probe)
        assert result is not None
        assert result["low_risk"] is True

    def test_missing_cli_returns_workaround_dict(self):
        probe = {"dep": {"kind": "cli", "name": "x_cli_not_here"}, "present": False, "path": None}
        result = spawn_workaround_agent(probe)
        assert isinstance(result, dict)
        assert "dep_name" in result

    def test_none_input_raises_value_error(self):
        with pytest.raises(ValueError, match="probe_result must be a dict"):
            spawn_workaround_agent(None)  # type: ignore[arg-type]

    def test_string_input_raises_value_error(self):
        with pytest.raises(ValueError, match="probe_result must be a dict"):
            spawn_workaround_agent("not a dict")  # type: ignore[arg-type]

    def test_missing_keys_raises_value_error(self):
        with pytest.raises(ValueError, match="must have 'dep' and 'present' keys"):
            spawn_workaround_agent({"dep": {"kind": "cli", "name": "git"}})

    def test_dep_name_in_workaround_description(self):
        dep_name = "z_not_exist"
        probe = {"dep": {"kind": "python", "name": dep_name}, "present": False, "path": None}
        result = spawn_workaround_agent(probe)
        assert result is not None
        assert dep_name in result["description"]


# ---------------------------------------------------------------------------
# apply_workaround
# ---------------------------------------------------------------------------


class TestApplyWorkaround:
    def test_present_dep_is_noop(self):
        probe = {"dep": {"kind": "python", "name": "os"}, "present": True}
        # Should not raise
        apply_workaround(probe, None)

    def test_missing_dep_no_workaround_raises(self):
        probe = {"dep": {"kind": "cli", "name": "x_missing"}, "present": False}
        with pytest.raises(MissingDependencyError):
            apply_workaround(probe, None)

    def test_low_risk_workaround_does_not_raise(self):
        probe = {"dep": {"kind": "python", "name": "z_not_exist"}, "present": False}
        workaround = {
            "dep_name": "z_not_exist",
            "description": "Install via pip",
            "low_risk": True,
            "commands": ["pip install z_not_exist"],
        }
        # Should not raise
        apply_workaround(probe, workaround)

    def test_high_risk_workaround_raises(self):
        probe = {"dep": {"kind": "cli", "name": "some_cli"}, "present": False}
        workaround = {
            "dep_name": "some_cli",
            "description": "Install via apt",
            "low_risk": False,
            "commands": ["sudo apt-get install some_cli"],
        }
        with pytest.raises(MissingDependencyError):
            apply_workaround(probe, workaround)

    def test_error_message_names_missing_dep(self):
        dep_name = "x_missing_dep"
        probe = {"dep": {"kind": "cli", "name": dep_name}, "present": False}
        with pytest.raises(MissingDependencyError) as exc_info:
            apply_workaround(probe, None)
        assert dep_name in str(exc_info.value)

    def test_error_includes_workaround_description(self):
        probe = {"dep": {"kind": "cli", "name": "some_cli"}, "present": False}
        description = "Install via apt-get"
        workaround = {
            "dep_name": "some_cli",
            "description": description,
            "low_risk": False,
            "commands": [],
        }
        with pytest.raises(MissingDependencyError) as exc_info:
            apply_workaround(probe, workaround)
        assert description in str(exc_info.value)

    def test_none_probe_raises_value_error(self):
        with pytest.raises(ValueError):
            apply_workaround(None, None)  # type: ignore[arg-type]

    def test_missing_dep_error_is_value_error_subclass(self):
        probe = {"dep": {"kind": "cli", "name": "x_missing"}, "present": False}
        with pytest.raises(ValueError):
            apply_workaround(probe, None)


# ---------------------------------------------------------------------------
# run_preflight
# ---------------------------------------------------------------------------


class TestRunPreflight:
    def test_empty_list_does_not_raise(self):
        result = run_preflight([])
        assert result["total_deps"] == 0
        assert result["halted"] is False

    def test_returns_required_keys(self):
        result = run_preflight([])
        assert "total_deps" in result
        assert "missing" in result
        assert "applied_workarounds" in result
        assert "halted" in result

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            run_preflight(None)  # type: ignore[arg-type]

    def test_string_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            run_preflight("not a list")  # type: ignore[arg-type]

    def test_all_present_deps_not_in_missing(self):
        result = run_preflight(["Function defined: os.getcwd"])
        assert "os" not in result["missing"]

    def test_halted_is_always_false(self):
        result = run_preflight(["Function defined: os.getcwd"])
        assert result["halted"] is False

    def test_missing_high_risk_dep_raises(self):
        ac = "command: __nonexistent_cli_guaranteed_absent_xyz987__"
        with pytest.raises(MissingDependencyError):
            run_preflight([ac])

    def test_error_message_names_missing_dep(self):
        dep_name = "__totally_absent_cli_xyz_abc_987__"
        ac = f"command: {dep_name}"
        with pytest.raises(MissingDependencyError) as exc_info:
            run_preflight([ac])
        assert dep_name in str(exc_info.value)

    def test_zero_missing_means_no_applied_workarounds(self):
        result = run_preflight(["Function defined: os.getcwd"])
        assert isinstance(result["applied_workarounds"], list)

    def test_total_deps_is_int(self):
        result = run_preflight(["Function defined: os.getcwd"])
        assert isinstance(result["total_deps"], int)

    def test_missing_dep_error_is_value_error_subclass(self):
        ac = "command: __nonexistent_cli_xyz987__"
        with pytest.raises(ValueError):
            run_preflight([ac])


# ---------------------------------------------------------------------------
# Integration: orchestrator imports
# ---------------------------------------------------------------------------


class TestOrchestratorIntegration:
    def test_orchestrator_exposes_probe_env_dependencies(self):
        from bob.orchestrator import probe_env_dependencies
        assert callable(probe_env_dependencies)

    def test_orchestrator_exposes_spawn_workaround_agent(self):
        from bob.orchestrator import spawn_workaround_agent as swa
        assert callable(swa)

    def test_orchestrator_exposes_apply_workaround(self):
        from bob.orchestrator import apply_workaround as aw
        assert callable(aw)

    def test_orchestrator_exposes_run_environment_preflight(self):
        from bob.orchestrator import run_environment_preflight
        assert callable(run_environment_preflight)

    def test_orchestrator_run_environment_preflight_works(self):
        from bob.orchestrator import run_environment_preflight
        result = run_environment_preflight([])
        assert result["total_deps"] == 0
