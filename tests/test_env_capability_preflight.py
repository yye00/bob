"""Tests for bob.env_capability_preflight.

Feature 9cea2d12: Environment-capability preflight with research-driven
workaround discovery. This module is the canonical entry point required by the
feature's acceptance criteria (src/bob/env_capability_preflight.py exposing
probe_dependencies and discover_workaround).
"""

import pytest

from bob.env_capability_preflight import (
    MissingDependencyError,
    apply_workaround,
    discover_workaround,
    enumerate_dependencies,
    probe_dependencies,
    probe_dependency,
    run_preflight,
)


class TestProbeDependencies:
    def test_empty_list_returns_empty(self):
        assert probe_dependencies([]) == []

    def test_python_stdlib_dep_is_present(self):
        result = probe_dependencies(["Function defined: os.getcwd"])
        os_probe = [r for r in result if r["dep"]["name"] == "os"]
        assert len(os_probe) == 1
        assert os_probe[0]["present"] is True

    def test_probe_result_shape(self):
        result = probe_dependencies(["Function defined: json.loads"])
        for r in result:
            assert "dep" in r
            assert "present" in r
            assert "path" in r

    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            probe_dependencies("not a list")


class TestDiscoverWorkaround:
    def test_present_dep_returns_none(self):
        probe = {"dep": {"kind": "python", "name": "os"}, "present": True, "path": "/x"}
        assert discover_workaround(probe) is None

    def test_missing_python_returns_low_risk_workaround(self):
        probe = {"dep": {"kind": "python", "name": "nope_mod"}, "present": False, "path": None}
        wk = discover_workaround(probe)
        assert wk["dep_name"] == "nope_mod"
        assert wk["low_risk"] is True
        assert any("pip install" in c for c in wk["commands"])

    def test_missing_cli_returns_high_risk_workaround(self):
        probe = {"dep": {"kind": "cli", "name": "some_absent_cli"}, "present": False, "path": None}
        wk = discover_workaround(probe)
        assert wk["dep_name"] == "some_absent_cli"
        assert wk["low_risk"] is False

    def test_invalid_input_raises(self):
        with pytest.raises(ValueError, match="probe_result must be a dict"):
            discover_workaround("not a dict")

    def test_missing_keys_raises(self):
        with pytest.raises(ValueError, match="must have 'dep' and 'present' keys"):
            discover_workaround({"dep": {"kind": "cli", "name": "git"}})


class TestApplyAndRun:
    def test_apply_present_is_noop(self):
        probe = {"dep": {"kind": "python", "name": "os"}, "present": True, "path": "/x"}
        assert apply_workaround(probe, None) is None

    def test_apply_low_risk_returns(self):
        probe = {"dep": {"kind": "python", "name": "nope_mod"}, "present": False, "path": None}
        wk = discover_workaround(probe)
        assert apply_workaround(probe, wk) is None

    def test_apply_high_risk_halts(self):
        probe = {"dep": {"kind": "cli", "name": "absent_cli_xyz"}, "present": False, "path": None}
        wk = discover_workaround(probe)
        with pytest.raises(MissingDependencyError, match="absent_cli_xyz"):
            apply_workaround(probe, wk)

    def test_run_preflight_empty(self):
        summary = run_preflight([])
        assert summary["total_deps"] == 0
        assert summary["halted"] is False

    def test_run_preflight_present_deps(self):
        summary = run_preflight(["Function defined: os.getcwd"])
        assert "os" not in summary["missing"]

    def test_run_preflight_high_risk_missing_halts(self):
        with pytest.raises(MissingDependencyError):
            run_preflight(["command: __definitely_absent_cli_abc987__"])


class TestOrchestratorIntegration:
    def test_orchestrator_exposes_probe(self):
        import bob.orchestrator as orch

        assert hasattr(orch, "probe_dependencies")

    def test_module_reexports_match_preflight(self):
        import bob.env_capability_preflight as feat
        import bob.preflight as base

        deps = feat.enumerate_dependencies(["Function defined: os.getcwd"])
        assert deps == base.enumerate_dependencies(["Function defined: os.getcwd"])
