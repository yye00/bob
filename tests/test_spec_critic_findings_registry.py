"""Tests for spec_critic.persist_findings — the spec_findings.yaml registry."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from bob3.spec_quality.spec_critic import (
    SpecDefect,
    critique_feature,
    persist_findings,
)


def _make_defect(
    feature_id: str = "feat-001",
    ac_index: int = 0,
    defect_type: str = "ambiguity",
) -> SpecDefect:
    return SpecDefect(
        feature_id=feature_id,
        ac_index=ac_index,
        defect_type=defect_type,
        rationale="test rationale",
        suggested_fix="test fix",
    )


class TestPersistFindings:
    def test_creates_file_if_not_exists(self, tmp_path):
        findings_file = tmp_path / "spec_findings.yaml"
        assert not findings_file.exists()
        persist_findings(
            [_make_defect()],
            feature_id="feat-001",
            name="Test",
            description="d",
            acceptance_criteria=["File exists: src/x.py"],
            path=findings_file,
        )
        assert findings_file.exists()

    def test_file_contains_valid_yaml(self, tmp_path):
        findings_file = tmp_path / "spec_findings.yaml"
        persist_findings(
            [_make_defect()],
            feature_id="feat-001",
            name="Test",
            description="d",
            acceptance_criteria=["File exists: src/x.py"],
            path=findings_file,
        )
        with open(findings_file) as fh:
            data = yaml.safe_load(fh)
        assert isinstance(data, dict)

    def test_returns_spec_hash_string(self, tmp_path):
        findings_file = tmp_path / "spec_findings.yaml"
        h = persist_findings(
            [],
            feature_id="feat-001",
            name="n",
            description="d",
            acceptance_criteria=[],
            path=findings_file,
        )
        assert isinstance(h, str)
        assert len(h) == 16  # SHA-256 truncated to 16 hex chars

    def test_same_spec_produces_same_hash(self, tmp_path):
        findings_file = tmp_path / "spec_findings.yaml"
        kwargs = dict(
            feature_id="feat-001",
            name="n",
            description="d",
            acceptance_criteria=["File exists: src/x.py"],
            path=findings_file,
        )
        h1 = persist_findings([], **kwargs)
        h2 = persist_findings([], **kwargs)
        assert h1 == h2

    def test_different_spec_produces_different_hash(self, tmp_path):
        findings_file = tmp_path / "spec_findings.yaml"
        h1 = persist_findings(
            [],
            feature_id="feat-001", name="A", description="d",
            acceptance_criteria=["File exists: src/a.py"],
            path=findings_file,
        )
        h2 = persist_findings(
            [],
            feature_id="feat-002", name="B", description="d",
            acceptance_criteria=["File exists: src/b.py"],
            path=findings_file,
        )
        assert h1 != h2

    def test_defects_stored_in_registry(self, tmp_path):
        findings_file = tmp_path / "spec_findings.yaml"
        defects = [_make_defect(defect_type="ambiguity"), _make_defect(ac_index=1, defect_type="untestable")]
        h = persist_findings(
            defects,
            feature_id="feat-001",
            name="n",
            description="d",
            acceptance_criteria=["x", "y"],
            path=findings_file,
        )
        with open(findings_file) as fh:
            data = yaml.safe_load(fh)
        entry = data["findings_by_hash"][h]
        assert entry["defect_count"] == 2
        assert len(entry["defects"]) == 2

    def test_schema_version_one(self, tmp_path):
        findings_file = tmp_path / "spec_findings.yaml"
        persist_findings([], path=findings_file)
        with open(findings_file) as fh:
            data = yaml.safe_load(fh)
        assert data["schema_version"] == 1

    def test_overwrite_same_hash_on_repeat_run(self, tmp_path):
        findings_file = tmp_path / "spec_findings.yaml"
        kwargs = dict(
            feature_id="feat-001", name="n", description="d",
            acceptance_criteria=["File exists: src/x.py"],
            path=findings_file,
        )
        persist_findings([_make_defect()], **kwargs)
        persist_findings([_make_defect(), _make_defect(ac_index=1)], **kwargs)

        with open(findings_file) as fh:
            data = yaml.safe_load(fh)
        hashes = list(data["findings_by_hash"].keys())
        assert len(hashes) == 1  # same hash → one entry
        assert data["findings_by_hash"][hashes[0]]["defect_count"] == 2

    def test_regression_flag_set_when_defects_increase(self, tmp_path):
        findings_file = tmp_path / "spec_findings.yaml"
        kwargs = dict(
            feature_id="feat-001", name="n", description="d",
            acceptance_criteria=["File exists: src/x.py"],
            path=findings_file,
        )
        # First run: 1 defect
        h = persist_findings([_make_defect()], **kwargs)
        # Second run: 2 defects (regression)
        persist_findings([_make_defect(), _make_defect(ac_index=2)], **kwargs)

        with open(findings_file) as fh:
            data = yaml.safe_load(fh)
        entry = data["findings_by_hash"][h]
        assert entry["regression"] is True
        assert entry["prior_defect_count"] == 1

    def test_regression_false_when_defects_decrease(self, tmp_path):
        findings_file = tmp_path / "spec_findings.yaml"
        kwargs = dict(
            feature_id="feat-001", name="n", description="d",
            acceptance_criteria=["File exists: src/x.py"],
            path=findings_file,
        )
        persist_findings([_make_defect(), _make_defect(ac_index=1)], **kwargs)
        h = persist_findings([_make_defect()], **kwargs)

        with open(findings_file) as fh:
            data = yaml.safe_load(fh)
        assert data["findings_by_hash"][h]["regression"] is False

    def test_empty_defects_stored_cleanly(self, tmp_path):
        findings_file = tmp_path / "spec_findings.yaml"
        h = persist_findings(
            [],
            feature_id="feat-001", name="n", description="d",
            acceptance_criteria=["File exists: src/x.py", "pytest: tests/test_x_error.py"],
            path=findings_file,
        )
        with open(findings_file) as fh:
            data = yaml.safe_load(fh)
        entry = data["findings_by_hash"][h]
        assert entry["defect_count"] == 0
        assert entry["defects"] == []

    def test_multiple_features_stored_separately(self, tmp_path):
        findings_file = tmp_path / "spec_findings.yaml"
        h1 = persist_findings(
            [_make_defect()],
            feature_id="feat-001", name="F1", description="d",
            acceptance_criteria=["x"],
            path=findings_file,
        )
        h2 = persist_findings(
            [],
            feature_id="feat-002", name="F2", description="d",
            acceptance_criteria=["y"],
            path=findings_file,
        )
        assert h1 != h2
        with open(findings_file) as fh:
            data = yaml.safe_load(fh)
        assert len(data["findings_by_hash"]) == 2


class TestIntegrationCritiqueAndPersist:
    def test_end_to_end_roundtrip(self, tmp_path):
        """critique_feature → persist_findings → verify stored content."""
        findings_file = tmp_path / "spec_findings.yaml"
        acs = ["The module works correctly"]
        defects = critique_feature(
            feature_id="e2e-001", name="End-to-end", description="d",
            acceptance_criteria=acs,
        )
        assert len(defects) > 0

        h = persist_findings(
            defects,
            feature_id="e2e-001", name="End-to-end", description="d",
            acceptance_criteria=acs,
            path=findings_file,
        )

        with open(findings_file) as fh:
            data = yaml.safe_load(fh)

        entry = data["findings_by_hash"][h]
        assert entry["feature_id"] == "e2e-001"
        assert entry["defect_count"] == len(defects)
        for stored, original in zip(entry["defects"], defects):
            assert stored["defect_type"] == original.defect_type
            assert stored["ac_index"] == original.ac_index
