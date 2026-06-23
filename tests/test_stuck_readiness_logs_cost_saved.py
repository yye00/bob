"""Tests for _record_cost_saved and _log_decomposition_reason."""

import json
import pathlib
import tempfile
from unittest.mock import patch, MagicMock, mock_open

import pytest
import yaml

from bob3.models import Feature
from bob3.orchestrator.run_loop import (
    _log_decomposition_reason,
    _record_cost_saved,
)


def make_feature(**kwargs):
    defaults = dict(
        id="feat-cost",
        project_id="proj-001",
        name="Cost Test Feature",
        status="ready",
        refinement_attempts=2,
        readiness_score=0.65,
        max_refinement_attempts=5,
        conf_spec_understanding=0.65,
        conf_impl_correctness=0.65,
        conf_test_adequacy=0.65,
    )
    defaults.update(kwargs)
    return Feature(**defaults)


class TestLogDecompositionReason:
    def test_writes_jsonl_entry(self, tmp_path):
        f = make_feature()
        runs_dir = tmp_path / "runs" / "round-1"
        runs_dir.mkdir(parents=True)
        decomp_file = runs_dir / "decompositions.jsonl"

        _log_decomposition_reason(
            feature=f,
            reason="refinement_attempts=2, readiness_score=0.65, no_improvement",
            runs_round_dir=str(runs_dir),
        )

        assert decomp_file.exists()
        line = decomp_file.read_text().strip()
        entry = json.loads(line)
        assert entry["feature_id"] == f.id
        assert "reason" in entry
        assert "timestamp" in entry

    def test_creates_parent_dirs(self, tmp_path):
        f = make_feature()
        runs_dir = tmp_path / "runs" / "new-round"
        # Directory does NOT exist yet

        _log_decomposition_reason(
            feature=f,
            reason="test reason",
            runs_round_dir=str(runs_dir),
        )

        decomp_file = runs_dir / "decompositions.jsonl"
        assert decomp_file.exists()

    def test_appends_multiple_entries(self, tmp_path):
        runs_dir = tmp_path / "runs" / "round-2"
        runs_dir.mkdir(parents=True)

        f1 = make_feature(id="feat-a", name="Feature A")
        f2 = make_feature(id="feat-b", name="Feature B")

        _log_decomposition_reason(f1, "reason1", runs_round_dir=str(runs_dir))
        _log_decomposition_reason(f2, "reason2", runs_round_dir=str(runs_dir))

        lines = (runs_dir / "decompositions.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2
        ids = [json.loads(l)["feature_id"] for l in lines]
        assert "feat-a" in ids
        assert "feat-b" in ids


class TestRecordCostSaved:
    def test_appends_to_metrics_yaml(self, tmp_path):
        f = make_feature()
        metrics_path = tmp_path / "metrics.yaml"
        metrics_path.write_text("auto_repair_rate: 0.4\n")

        _record_cost_saved(
            feature=f,
            estimated_cost_avoided=1.5,
            metrics_path=str(metrics_path),
        )

        content = yaml.safe_load(metrics_path.read_text())
        assert "eval_treadmill_avoided_cost" in content
        assert len(content["eval_treadmill_avoided_cost"]) == 1
        entry = content["eval_treadmill_avoided_cost"][0]
        assert entry["feature_id"] == f.id
        assert entry["cost_avoided"] == 1.5

    def test_appends_to_existing_list(self, tmp_path):
        f = make_feature()
        metrics_path = tmp_path / "metrics.yaml"
        existing = {
            "eval_treadmill_avoided_cost": [
                {"feature_id": "feat-old", "cost_avoided": 0.5}
            ]
        }
        metrics_path.write_text(yaml.dump(existing))

        _record_cost_saved(
            feature=f,
            estimated_cost_avoided=2.0,
            metrics_path=str(metrics_path),
        )

        content = yaml.safe_load(metrics_path.read_text())
        assert len(content["eval_treadmill_avoided_cost"]) == 2

    def test_creates_metrics_file_if_missing(self, tmp_path):
        f = make_feature()
        metrics_path = tmp_path / "metrics.yaml"
        assert not metrics_path.exists()

        _record_cost_saved(
            feature=f,
            estimated_cost_avoided=1.0,
            metrics_path=str(metrics_path),
        )

        content = yaml.safe_load(metrics_path.read_text())
        assert "eval_treadmill_avoided_cost" in content
