"""Tests for discover_workaround — specifically the sqlite3 Python module workaround."""
from bob.orchestrator.env_preflight import (
    DepEntry,
    ProbeResult,
    Workaround,
    discover_workaround,
    spawns_research_subagent,
)


class TestSpawnsResearchSubagent:
    def test_returns_true(self):
        assert spawns_research_subagent() is True


class TestDiscoverWorkaroundReturnValue:
    def test_returns_none_for_present_dep(self):
        dep = DepEntry(kind="python", name="os")
        pr = ProbeResult(dep=dep, present=True, path="/usr/lib/python3/os.py")
        result = discover_workaround(pr)
        assert result is None

    def test_returns_workaround_for_missing_dep(self):
        dep = DepEntry(kind="python", name="__missing_pkg_xyz__")
        pr = ProbeResult(dep=dep, present=False)
        result = discover_workaround(pr)
        assert isinstance(result, Workaround)

    def test_workaround_has_dep_name(self):
        dep = DepEntry(kind="python", name="__missing_pkg_xyz__")
        pr = ProbeResult(dep=dep, present=False)
        result = discover_workaround(pr)
        assert result is not None
        assert result.dep_name == "__missing_pkg_xyz__"

    def test_workaround_has_description(self):
        dep = DepEntry(kind="python", name="requests")
        pr = ProbeResult(dep=dep, present=False)
        result = discover_workaround(pr)
        assert result is not None
        assert len(result.description) > 0


class TestSqlite3Workaround:
    def test_sqlite3_workaround_is_low_risk(self):
        dep = DepEntry(kind="python", name="sqlite3")
        pr = ProbeResult(dep=dep, present=False)
        result = discover_workaround(pr)
        assert result is not None
        assert result.low_risk is True

    def test_sqlite3_workaround_has_commands(self):
        dep = DepEntry(kind="python", name="sqlite3")
        pr = ProbeResult(dep=dep, present=False)
        result = discover_workaround(pr)
        assert result is not None
        assert isinstance(result.commands, list)
        assert len(result.commands) > 0

    def test_sqlite3_workaround_description_not_empty(self):
        dep = DepEntry(kind="python", name="sqlite3")
        pr = ProbeResult(dep=dep, present=False)
        result = discover_workaround(pr)
        assert result is not None
        assert "sqlite3" in result.description.lower() or "sqlite" in result.description.lower()


class TestCliWorkaround:
    def test_xxd_workaround_is_not_low_risk(self):
        dep = DepEntry(kind="cli", name="xxd")
        pr = ProbeResult(dep=dep, present=False)
        result = discover_workaround(pr)
        assert result is not None
        assert result.low_risk is False

    def test_xxd_workaround_names_dep(self):
        dep = DepEntry(kind="cli", name="xxd")
        pr = ProbeResult(dep=dep, present=False)
        result = discover_workaround(pr)
        assert result is not None
        assert result.dep_name == "xxd"

    def test_generic_cli_workaround_returned(self):
        dep = DepEntry(kind="cli", name="some_unknown_tool_abc")
        pr = ProbeResult(dep=dep, present=False)
        result = discover_workaround(pr)
        assert result is not None
        assert isinstance(result, Workaround)
