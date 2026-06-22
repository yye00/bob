"""Tests for public_registry_release_versioned_artifact_export."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import yaml

from bob3.public_registry_release_versioned_artifact_export import (
    ARTIFACT_SCHEMA_VERSION,
    export_public_registry,
    load_public_registry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_findings_yaml(tmp_path: Path, num_findings: int = 2) -> Path:
    findings_dir = tmp_path / "reviews"
    findings_dir.mkdir(parents=True)
    findings_file = findings_dir / "findings.yaml"
    findings = {
        "schema_version": 1,
        "findings": [
            {
                "id": f"R1-{i:03d}",
                "title": f"Finding {i}",
                "pattern": f"pattern-{i}",
                "files": [f"src/file_{i}.py"],
                "severity": "medium",
                "status": "fixed" if i % 2 == 0 else "open",
                "tags": [f"tag-{i}"],
                "notes": f"Note for finding {i}",
            }
            for i in range(1, num_findings + 1)
        ],
    }
    findings_file.write_text(yaml.dump(findings), encoding="utf-8")
    return findings_dir


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

def test_artifact_schema_version_is_string():
    assert isinstance(ARTIFACT_SCHEMA_VERSION, str)
    assert len(ARTIFACT_SCHEMA_VERSION) > 0


# ---------------------------------------------------------------------------
# export_public_registry basic
# ---------------------------------------------------------------------------

def test_export_creates_yaml_file(tmp_path):
    findings_dir = _make_findings_yaml(tmp_path)
    out_path = tmp_path / "release" / "findings_v1.yaml"
    export_public_registry(
        out_path=out_path,
        findings_path=findings_dir / "findings.yaml",
    )
    assert out_path.exists()


def test_export_yaml_is_valid(tmp_path):
    findings_dir = _make_findings_yaml(tmp_path)
    out_path = tmp_path / "release.yaml"
    export_public_registry(
        out_path=out_path,
        findings_path=findings_dir / "findings.yaml",
    )
    doc = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)


def test_export_contains_artifact_schema_version(tmp_path):
    findings_dir = _make_findings_yaml(tmp_path)
    out_path = tmp_path / "release.yaml"
    export_public_registry(
        out_path=out_path,
        findings_path=findings_dir / "findings.yaml",
    )
    doc = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert "artifact_schema_version" in doc
    assert doc["artifact_schema_version"] == ARTIFACT_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Provenance metadata
# ---------------------------------------------------------------------------

def test_export_contains_provenance(tmp_path):
    findings_dir = _make_findings_yaml(tmp_path)
    out_path = tmp_path / "release.yaml"
    export_public_registry(
        out_path=out_path,
        findings_path=findings_dir / "findings.yaml",
    )
    doc = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert "provenance" in doc
    prov = doc["provenance"]
    assert "bob_version" in prov
    assert "timestamp" in prov
    assert "experiment_run_ids" in prov


def test_export_bob_version_is_string(tmp_path):
    findings_dir = _make_findings_yaml(tmp_path)
    out_path = tmp_path / "release.yaml"
    export_public_registry(
        out_path=out_path,
        findings_path=findings_dir / "findings.yaml",
    )
    doc = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert isinstance(doc["provenance"]["bob_version"], str)
    assert len(doc["provenance"]["bob_version"]) > 0


def test_export_timestamp_is_iso8601(tmp_path):
    findings_dir = _make_findings_yaml(tmp_path)
    out_path = tmp_path / "release.yaml"
    export_public_registry(
        out_path=out_path,
        findings_path=findings_dir / "findings.yaml",
    )
    doc = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    ts = doc["provenance"]["timestamp"]
    # ISO 8601 datetime strings contain 'T'
    assert "T" in ts or "-" in ts


def test_export_experiment_run_ids_is_list(tmp_path):
    findings_dir = _make_findings_yaml(tmp_path)
    out_path = tmp_path / "release.yaml"
    export_public_registry(
        out_path=out_path,
        findings_path=findings_dir / "findings.yaml",
    )
    doc = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert isinstance(doc["provenance"]["experiment_run_ids"], list)


def test_export_with_explicit_run_ids(tmp_path):
    findings_dir = _make_findings_yaml(tmp_path)
    out_path = tmp_path / "release.yaml"
    run_ids = ["run-abc", "run-def"]
    export_public_registry(
        out_path=out_path,
        findings_path=findings_dir / "findings.yaml",
        experiment_run_ids=run_ids,
    )
    doc = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert doc["provenance"]["experiment_run_ids"] == run_ids


# ---------------------------------------------------------------------------
# Findings content
# ---------------------------------------------------------------------------

def test_export_contains_findings(tmp_path):
    findings_dir = _make_findings_yaml(tmp_path, num_findings=3)
    out_path = tmp_path / "release.yaml"
    export_public_registry(
        out_path=out_path,
        findings_path=findings_dir / "findings.yaml",
    )
    doc = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert "findings" in doc
    assert len(doc["findings"]) == 3


def test_export_finding_has_required_fields(tmp_path):
    findings_dir = _make_findings_yaml(tmp_path)
    out_path = tmp_path / "release.yaml"
    export_public_registry(
        out_path=out_path,
        findings_path=findings_dir / "findings.yaml",
    )
    doc = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    finding = doc["findings"][0]
    for field in ("id", "title", "pattern", "severity", "status"):
        assert field in finding, f"Missing field: {field}"


def test_export_summary_stats(tmp_path):
    findings_dir = _make_findings_yaml(tmp_path, num_findings=4)
    out_path = tmp_path / "release.yaml"
    export_public_registry(
        out_path=out_path,
        findings_path=findings_dir / "findings.yaml",
    )
    doc = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert "summary" in doc
    assert doc["summary"]["total_findings"] == 4


# ---------------------------------------------------------------------------
# load_public_registry round-trip
# ---------------------------------------------------------------------------

def test_load_round_trip(tmp_path):
    findings_dir = _make_findings_yaml(tmp_path, num_findings=2)
    out_path = tmp_path / "release.yaml"
    export_public_registry(
        out_path=out_path,
        findings_path=findings_dir / "findings.yaml",
    )
    doc = load_public_registry(out_path)
    assert doc["provenance"]["bob_version"] is not None
    assert len(doc["findings"]) == 2


def test_load_raises_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_public_registry(tmp_path / "nonexistent.yaml")


def test_load_raises_on_schema_mismatch(tmp_path):
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text(yaml.dump({"artifact_schema_version": "999.0", "findings": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        load_public_registry(bad_yaml)


# ---------------------------------------------------------------------------
# Output directory is created automatically
# ---------------------------------------------------------------------------

def test_export_creates_parent_directories(tmp_path):
    findings_dir = _make_findings_yaml(tmp_path)
    out_path = tmp_path / "deep" / "nested" / "dir" / "release.yaml"
    export_public_registry(
        out_path=out_path,
        findings_path=findings_dir / "findings.yaml",
    )
    assert out_path.exists()


# ---------------------------------------------------------------------------
# Empty findings
# ---------------------------------------------------------------------------

def test_export_empty_findings(tmp_path):
    findings_dir = tmp_path / "reviews"
    findings_dir.mkdir()
    findings_file = findings_dir / "findings.yaml"
    findings_file.write_text(yaml.dump({"schema_version": 1, "findings": []}), encoding="utf-8")
    out_path = tmp_path / "release.yaml"
    export_public_registry(
        out_path=out_path,
        findings_path=findings_file,
    )
    doc = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert doc["findings"] == []
    assert doc["summary"]["total_findings"] == 0
