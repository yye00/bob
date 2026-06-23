"""Tests for persist_applied_workarounds — writes runs/<round>/applied_workarounds.yaml."""
import pathlib
import tempfile

import yaml
import pytest

from bob3.orchestrator.env_preflight import Workaround, persist_applied_workarounds


class TestPersistAppliedWorkarounds:
    def test_creates_output_file(self, tmp_path):
        workarounds = [
            Workaround(
                dep_name="yaml",
                description="Install PyYAML via pip",
                low_risk=True,
                commands=["pip install pyyaml"],
            )
        ]
        out = persist_applied_workarounds(workarounds, round_num=1, workspace=tmp_path)
        assert out.exists()

    def test_output_path_is_correct(self, tmp_path):
        workarounds = [
            Workaround(
                dep_name="click",
                description="Install click via pip",
                low_risk=True,
                commands=["pip install click"],
            )
        ]
        out = persist_applied_workarounds(workarounds, round_num=5, workspace=tmp_path)
        expected = tmp_path / "runs" / "5" / "applied_workarounds.yaml"
        assert out == expected

    def test_output_is_valid_yaml(self, tmp_path):
        workarounds = [
            Workaround(
                dep_name="requests",
                description="pip install requests",
                low_risk=True,
                commands=["pip install requests"],
            )
        ]
        out = persist_applied_workarounds(workarounds, round_num=1, workspace=tmp_path)
        data = yaml.safe_load(out.read_text())
        assert isinstance(data, dict)

    def test_output_has_applied_workarounds_key(self, tmp_path):
        workarounds = [
            Workaround(
                dep_name="sqlite3",
                description="stdlib module",
                low_risk=True,
                commands=[],
            )
        ]
        out = persist_applied_workarounds(workarounds, round_num=2, workspace=tmp_path)
        data = yaml.safe_load(out.read_text())
        assert "applied_workarounds" in data

    def test_output_contains_dep_name(self, tmp_path):
        workarounds = [
            Workaround(
                dep_name="my_dep",
                description="Install my_dep",
                low_risk=True,
                commands=["pip install my_dep"],
            )
        ]
        out = persist_applied_workarounds(workarounds, round_num=3, workspace=tmp_path)
        data = yaml.safe_load(out.read_text())
        records = data["applied_workarounds"]
        assert any(r["dep_name"] == "my_dep" for r in records)

    def test_multiple_workarounds_persisted(self, tmp_path):
        workarounds = [
            Workaround(dep_name="a", description="desc a", low_risk=True, commands=[]),
            Workaround(dep_name="b", description="desc b", low_risk=False, commands=["apt install b"]),
        ]
        out = persist_applied_workarounds(workarounds, round_num=7, workspace=tmp_path)
        data = yaml.safe_load(out.read_text())
        records = data["applied_workarounds"]
        assert len(records) == 2

    def test_empty_workarounds_writes_empty_list(self, tmp_path):
        out = persist_applied_workarounds([], round_num=1, workspace=tmp_path)
        data = yaml.safe_load(out.read_text())
        assert data["applied_workarounds"] == []

    def test_returns_path_object(self, tmp_path):
        out = persist_applied_workarounds([], round_num=1, workspace=tmp_path)
        assert isinstance(out, pathlib.Path)

    def test_creates_parent_dirs(self, tmp_path):
        out = persist_applied_workarounds([], round_num=99, workspace=tmp_path)
        assert (tmp_path / "runs" / "99").is_dir()
