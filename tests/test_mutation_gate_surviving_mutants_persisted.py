"""Tests for persist_surviving_mutants — AC-17."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bob3.verification.mutation_gate import MutationReport, persist_surviving_mutants


class TestPersistSurvivingMutants:
    def _make_report(self, feature_id="feat-abc", score=0.60, diffs=None):
        return MutationReport(
            feature_id=feature_id,
            total_mutants=10,
            killed=6,
            survived=4,
            timed_out=0,
            mutation_score=score,
            surviving_mutant_diffs=diffs or [
                {"mutant_id": "src__foo__1", "diff": "--- a/src/foo.py\n+++ b/src/foo.py\n@@ -1 +1 @@\n-    x > 0\n+    x >= 0\n"},
            ],
        )

    def test_writes_json_file(self, tmp_path):
        report = self._make_report()
        path = persist_surviving_mutants(report, tmp_path)
        assert path.exists()
        assert path.suffix == ".json"

    def test_file_is_in_runs_feature_dir(self, tmp_path):
        report = self._make_report(feature_id="my-feature-123")
        path = persist_surviving_mutants(report, tmp_path)
        assert path.parent == tmp_path / "runs" / "my-feature-123"

    def test_file_is_named_mutation_report_json(self, tmp_path):
        report = self._make_report()
        path = persist_surviving_mutants(report, tmp_path)
        assert path.name == "mutation_report.json"

    def test_json_contains_mutation_score(self, tmp_path):
        report = self._make_report(score=0.60)
        path = persist_surviving_mutants(report, tmp_path)
        data = json.loads(path.read_text())
        assert "mutation_score" in data
        assert data["mutation_score"] == pytest.approx(0.60)

    def test_json_contains_feature_id(self, tmp_path):
        report = self._make_report(feature_id="feat-xyz")
        path = persist_surviving_mutants(report, tmp_path)
        data = json.loads(path.read_text())
        assert data["feature_id"] == "feat-xyz"

    def test_json_contains_surviving_mutant_diffs(self, tmp_path):
        diff = {"mutant_id": "m1", "diff": "--- old\n+++ new\n@@ -1 +1 @@\n-x\n+y\n"}
        report = self._make_report(diffs=[diff])
        path = persist_surviving_mutants(report, tmp_path)
        data = json.loads(path.read_text())
        assert "surviving_mutant_diffs" in data
        assert len(data["surviving_mutant_diffs"]) == 1
        assert data["surviving_mutant_diffs"][0]["mutant_id"] == "m1"
        assert "diff" in data["surviving_mutant_diffs"][0]

    def test_json_contains_message_about_strengthening(self, tmp_path):
        report = self._make_report()
        path = persist_surviving_mutants(report, tmp_path)
        data = json.loads(path.read_text())
        assert "message" in data
        assert "strengthen" in data["message"].lower() or "assertions" in data["message"].lower()

    def test_creates_parent_dirs(self, tmp_path):
        workspace = tmp_path / "nonexistent" / "workspace"
        report = self._make_report(feature_id="f1")
        path = persist_surviving_mutants(report, workspace)
        assert path.exists()

    def test_returns_path_object(self, tmp_path):
        report = self._make_report()
        result = persist_surviving_mutants(report, tmp_path)
        assert isinstance(result, Path)

    def test_json_contains_total_and_counts(self, tmp_path):
        report = self._make_report()
        path = persist_surviving_mutants(report, tmp_path)
        data = json.loads(path.read_text())
        assert data["total_mutants"] == 10
        assert data["killed"] == 6
        assert data["survived"] == 4
