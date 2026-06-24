"""Tests for probe() — detects present and missing CLIs and Python modules."""
import sys

import pytest

from bob.orchestrator.env_preflight import DepEntry, ProbeResult, probe


class TestProbeCliDeps:
    def test_detects_present_cli(self):
        # python3 is guaranteed present
        dep = DepEntry(kind="cli", name="python3")
        result = probe(dep)
        assert isinstance(result, ProbeResult)
        assert result.present is True
        assert result.dep is dep

    def test_detects_missing_cli(self):
        # Use a name that is certainly not installed
        dep = DepEntry(kind="cli", name="__definitely_not_installed_cli_xyz__")
        result = probe(dep)
        assert isinstance(result, ProbeResult)
        assert result.present is False

    def test_present_cli_has_path(self):
        dep = DepEntry(kind="cli", name="python3")
        result = probe(dep)
        assert result.path is not None
        assert len(result.path) > 0

    def test_missing_cli_path_is_none(self):
        dep = DepEntry(kind="cli", name="__no_such_cli_qwerty__")
        result = probe(dep)
        assert result.path is None


class TestProbePythonDeps:
    def test_detects_present_python_module(self):
        dep = DepEntry(kind="python", name="os")
        result = probe(dep)
        assert isinstance(result, ProbeResult)
        assert result.present is True

    def test_detects_missing_python_module(self):
        dep = DepEntry(kind="python", name="__no_such_module_xyz12345__")
        result = probe(dep)
        assert isinstance(result, ProbeResult)
        assert result.present is False

    def test_stdlib_module_sqlite3_present(self):
        dep = DepEntry(kind="python", name="sqlite3")
        result = probe(dep)
        assert result.present is True

    def test_returns_probe_result_type(self):
        dep = DepEntry(kind="python", name="json")
        result = probe(dep)
        assert isinstance(result, ProbeResult)

    def test_probe_result_has_dep_reference(self):
        dep = DepEntry(kind="cli", name="ls")
        result = probe(dep)
        assert result.dep is dep


class TestProbeUnknownKind:
    def test_unknown_kind_raises(self):
        dep = DepEntry(kind="unknown_kind", name="something")
        with pytest.raises(ValueError, match="Unknown dep kind"):
            probe(dep)
