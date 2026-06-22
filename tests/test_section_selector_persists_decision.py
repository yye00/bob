"""Tests: persist_decision appends records to reviews/section_selections.yaml."""

from __future__ import annotations

import yaml
import pytest

from bob3.spec_quality.section_selector import (
    SectionSchemaError,
    module_set,
    persist_decision,
)


def _valid_section_map() -> dict[str, str]:
    m = {s: "OPTIONAL" for s in module_set()}
    m["functional"] = "REQUIRED"
    return m


class TestPersistDecision:
    def test_creates_file_when_absent(self, tmp_path):
        out_path = tmp_path / "section_selections.yaml"
        result = persist_decision(
            "feat-001", "My Feature", _valid_section_map(), output_path=out_path
        )
        assert result == out_path
        assert out_path.exists()

    def test_written_yaml_has_decisions_key(self, tmp_path):
        out_path = tmp_path / "section_selections.yaml"
        persist_decision("feat-001", "My Feature", _valid_section_map(), output_path=out_path)
        data = yaml.safe_load(out_path.read_text())
        assert "decisions" in data

    def test_first_record_has_expected_fields(self, tmp_path):
        out_path = tmp_path / "section_selections.yaml"
        section_map = _valid_section_map()
        persist_decision("feat-abc", "Test Feature", section_map, output_path=out_path)
        data = yaml.safe_load(out_path.read_text())
        record = data["decisions"][0]
        assert record["feature_id"] == "feat-abc"
        assert record["name"] == "Test Feature"
        assert "timestamp" in record
        assert record["sections"] == section_map

    def test_appends_to_existing_file(self, tmp_path):
        out_path = tmp_path / "section_selections.yaml"
        persist_decision("feat-001", "First", _valid_section_map(), output_path=out_path)
        persist_decision("feat-002", "Second", _valid_section_map(), output_path=out_path)
        data = yaml.safe_load(out_path.read_text())
        assert len(data["decisions"]) == 2
        assert data["decisions"][0]["feature_id"] == "feat-001"
        assert data["decisions"][1]["feature_id"] == "feat-002"

    def test_creates_parent_dirs(self, tmp_path):
        out_path = tmp_path / "nested" / "deep" / "section_selections.yaml"
        persist_decision("feat-001", "My Feature", _valid_section_map(), output_path=out_path)
        assert out_path.exists()

    def test_returns_path_object(self, tmp_path):
        out_path = tmp_path / "section_selections.yaml"
        result = persist_decision("feat-001", "My Feature", _valid_section_map(), output_path=out_path)
        from pathlib import Path
        assert isinstance(result, Path)

    def test_rejects_invalid_section_map(self, tmp_path):
        out_path = tmp_path / "section_selections.yaml"
        bad_map = {"functional": "REQUIRED"}  # missing sections
        with pytest.raises(SectionSchemaError):
            persist_decision("feat-001", "My Feature", bad_map, output_path=out_path)

    def test_sections_stored_as_dict(self, tmp_path):
        out_path = tmp_path / "section_selections.yaml"
        section_map = _valid_section_map()
        persist_decision("feat-001", "My Feature", section_map, output_path=out_path)
        data = yaml.safe_load(out_path.read_text())
        stored_sections = data["decisions"][0]["sections"]
        assert isinstance(stored_sections, dict)
        assert set(stored_sections.keys()) == set(module_set())

    def test_timestamp_ends_with_z(self, tmp_path):
        out_path = tmp_path / "section_selections.yaml"
        persist_decision("feat-001", "My Feature", _valid_section_map(), output_path=out_path)
        data = yaml.safe_load(out_path.read_text())
        ts = data["decisions"][0]["timestamp"]
        assert ts.endswith("Z")
