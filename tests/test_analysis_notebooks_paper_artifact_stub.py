"""Tests for analysis_notebooks_paper_artifact_stub module.

Covers: telemetry loading, ECE computation, reliability diagram data,
bootstrap CI estimation, and ablation table generation.
"""

from __future__ import annotations

import json
import math
import pathlib
import tempfile

import pytest

from bob3.analysis_notebooks_paper_artifact_stub import (
    VERSION_LABELS,
    AblationRow,
    ReliabilityBucket,
    RunRecord,
    ablation_table,
    bootstrap_ci,
    compute_ece,
    load_run_jsonl,
    reliability_diagram_data,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_jsonl(tmp_path: pathlib.Path, records: list[dict]) -> pathlib.Path:
    p = tmp_path / "run.jsonl"
    with p.open("w") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    return p


def _make_record(
    feature_id: str = "f1",
    feature_name: str = "Feature 1",
    outcome: str = "completed",
    confidence: float | None = None,
    version: str | None = "V1",
    duration_ms: int | None = None,
    cost_usd: float | None = None,
    num_turns: int | None = None,
) -> dict:
    d: dict = {
        "feature_id": feature_id,
        "feature_name": feature_name,
        "outcome": outcome,
    }
    if confidence is not None:
        d["confidence"] = confidence
    if version is not None:
        d["version"] = version
    if duration_ms is not None:
        d["duration_ms"] = duration_ms
    if cost_usd is not None:
        d["cost_usd"] = cost_usd
    if num_turns is not None:
        d["num_turns"] = num_turns
    return d


# ---------------------------------------------------------------------------
# RunRecord data model
# ---------------------------------------------------------------------------


class TestRunRecord:
    def test_success_true_when_completed(self):
        rec = RunRecord(
            feature_id="x",
            feature_name="F",
            outcome="completed",
            confidence=None,
            version="V1",
            duration_ms=None,
            cost_usd=None,
            num_turns=None,
        )
        assert rec.success is True

    def test_success_false_when_failed(self):
        rec = RunRecord(
            feature_id="x",
            feature_name="F",
            outcome="failed",
            confidence=None,
            version="V1",
            duration_ms=None,
            cost_usd=None,
            num_turns=None,
        )
        assert rec.success is False

    def test_success_false_when_needs_human(self):
        rec = RunRecord(
            feature_id="x",
            feature_name="F",
            outcome="needs_human",
            confidence=None,
            version="V1",
            duration_ms=None,
            cost_usd=None,
            num_turns=None,
        )
        assert rec.success is False


# ---------------------------------------------------------------------------
# load_run_jsonl
# ---------------------------------------------------------------------------


class TestLoadRunJsonl:
    def test_loads_basic_record(self, tmp_path):
        p = _write_jsonl(tmp_path, [_make_record()])
        records = load_run_jsonl(p)
        assert len(records) == 1
        assert records[0].feature_id == "f1"
        assert records[0].outcome == "completed"
        assert records[0].success is True

    def test_loads_multiple_records(self, tmp_path):
        rows = [
            _make_record(feature_id="a", outcome="completed"),
            _make_record(feature_id="b", outcome="failed"),
            _make_record(feature_id="c", outcome="completed"),
        ]
        p = _write_jsonl(tmp_path, rows)
        records = load_run_jsonl(p)
        assert len(records) == 3
        assert [r.feature_id for r in records] == ["a", "b", "c"]

    def test_skips_blank_lines(self, tmp_path):
        p = tmp_path / "run.jsonl"
        p.write_text('\n{"feature_id":"x","feature_name":"F","outcome":"completed"}\n\n')
        records = load_run_jsonl(p)
        assert len(records) == 1

    def test_skips_comment_lines(self, tmp_path):
        p = tmp_path / "run.jsonl"
        p.write_text('# comment\n{"feature_id":"x","feature_name":"F","outcome":"completed"}\n')
        records = load_run_jsonl(p)
        assert len(records) == 1

    def test_parses_optional_fields(self, tmp_path):
        row = _make_record(
            confidence=0.85,
            version="V2",
            duration_ms=5000,
            cost_usd=0.42,
            num_turns=7,
        )
        p = _write_jsonl(tmp_path, [row])
        rec = load_run_jsonl(p)[0]
        assert rec.confidence == pytest.approx(0.85)
        assert rec.version == "V2"
        assert rec.duration_ms == 5000
        assert rec.cost_usd == pytest.approx(0.42)
        assert rec.num_turns == 7

    def test_missing_optional_fields_are_none(self, tmp_path):
        p = _write_jsonl(tmp_path, [_make_record()])
        rec = load_run_jsonl(p)[0]
        assert rec.confidence is None
        assert rec.duration_ms is None
        assert rec.cost_usd is None
        assert rec.num_turns is None

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_run_jsonl(tmp_path / "nonexistent.jsonl")

    def test_invalid_json_raises_value_error(self, tmp_path):
        p = tmp_path / "bad.jsonl"
        p.write_text("not-json\n")
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_run_jsonl(p)

    def test_empty_file_returns_empty_list(self, tmp_path):
        p = tmp_path / "empty.jsonl"
        p.write_text("")
        assert load_run_jsonl(p) == []

    def test_raw_field_preserved(self, tmp_path):
        row = _make_record(cost_usd=1.23)
        p = _write_jsonl(tmp_path, [row])
        rec = load_run_jsonl(p)[0]
        assert "cost_usd" in rec.raw


# ---------------------------------------------------------------------------
# compute_ece
# ---------------------------------------------------------------------------


class TestComputeEce:
    def test_perfect_calibration(self):
        # Confidence 0.5, 50% accuracy → ECE ≈ 0
        confidences = [0.5] * 100
        outcomes = [True] * 50 + [False] * 50
        ece = compute_ece(confidences, outcomes, n_bins=10)
        assert ece == pytest.approx(0.0, abs=0.02)

    def test_overconfident(self):
        # Always predict 1.0, but half are wrong → ECE = 0.5
        confidences = [1.0] * 10
        outcomes = [True] * 5 + [False] * 5
        ece = compute_ece(confidences, outcomes, n_bins=10)
        assert ece == pytest.approx(0.5, abs=0.01)

    def test_empty_returns_zero(self):
        assert compute_ece([], [], n_bins=10) == 0.0

    def test_mismatched_lengths_raise(self):
        with pytest.raises(ValueError, match="same length"):
            compute_ece([0.5, 0.5], [True], n_bins=10)

    def test_invalid_n_bins_raises(self):
        with pytest.raises(ValueError, match="n_bins"):
            compute_ece([0.5], [True], n_bins=0)

    def test_ece_in_range(self):
        import random as _rng
        _rng.seed(0)
        confs = [_rng.random() for _ in range(200)]
        outcomes = [_rng.random() < c for c in confs]
        ece = compute_ece(confs, outcomes, n_bins=10)
        assert 0.0 <= ece <= 1.0

    def test_single_sample(self):
        ece = compute_ece([0.8], [True], n_bins=10)
        assert ece == pytest.approx(0.2, abs=0.01)

    def test_confidence_clamped_at_boundary(self):
        # Confidence exactly 1.0 should not raise IndexError
        ece = compute_ece([1.0, 0.0], [True, False], n_bins=10)
        assert 0.0 <= ece <= 1.0


# ---------------------------------------------------------------------------
# reliability_diagram_data
# ---------------------------------------------------------------------------


class TestReliabilityDiagramData:
    def test_returns_n_bins_buckets(self):
        confs = [0.1, 0.5, 0.9]
        outcomes = [False, True, True]
        buckets = reliability_diagram_data(confs, outcomes, n_bins=5)
        assert len(buckets) == 5

    def test_bucket_types(self):
        buckets = reliability_diagram_data([0.5], [True], n_bins=10)
        for b in buckets:
            assert isinstance(b, ReliabilityBucket)

    def test_accuracy_in_range(self):
        import random as _rng
        _rng.seed(1)
        confs = [_rng.random() for _ in range(100)]
        outcomes = [_rng.random() < 0.7 for _ in range(100)]
        buckets = reliability_diagram_data(confs, outcomes, n_bins=10)
        for b in buckets:
            assert 0.0 <= b.accuracy <= 1.0

    def test_empty_bucket_has_zero_count(self):
        # All confidences in [0.8, 1.0] → first bins empty
        buckets = reliability_diagram_data([0.9, 0.95], [True, False], n_bins=10)
        assert buckets[0].count == 0
        assert buckets[0].accuracy == 0.0

    def test_total_count_matches_input(self):
        confs = [0.1, 0.3, 0.6, 0.8, 0.9]
        outcomes = [True, False, True, True, False]
        buckets = reliability_diagram_data(confs, outcomes, n_bins=5)
        assert sum(b.count for b in buckets) == 5

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError, match="same length"):
            reliability_diagram_data([0.5], [True, False], n_bins=10)

    def test_invalid_n_bins_raises(self):
        with pytest.raises(ValueError, match="n_bins"):
            reliability_diagram_data([0.5], [True], n_bins=0)

    def test_bucket_bounds_cover_zero_to_one(self):
        buckets = reliability_diagram_data([0.5], [True], n_bins=4)
        assert buckets[0].lower == pytest.approx(0.0)
        assert buckets[-1].upper == pytest.approx(1.0)

    def test_perfect_accuracy_in_high_bin(self):
        # All high-confidence predictions succeed
        confs = [0.95, 0.98, 0.99]
        outcomes = [True, True, True]
        buckets = reliability_diagram_data(confs, outcomes, n_bins=10)
        last = buckets[-1]
        assert last.count == 3
        assert last.accuracy == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# bootstrap_ci
# ---------------------------------------------------------------------------


class TestBootstrapCi:
    def test_mean_ci_contains_true_mean(self):
        data = [1.0] * 50 + [0.0] * 50
        lo, hi = bootstrap_ci(data, statistic=lambda xs: sum(xs) / len(xs), seed=0)
        assert lo <= 0.5 <= hi

    def test_ci_ordered(self):
        data = [float(i) for i in range(20)]
        lo, hi = bootstrap_ci(data, statistic=lambda xs: sum(xs) / len(xs), seed=1)
        assert lo <= hi

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            bootstrap_ci([], statistic=lambda xs: 0.0)

    def test_invalid_n_bootstrap_raises(self):
        with pytest.raises(ValueError, match="n_bootstrap"):
            bootstrap_ci([1.0], statistic=lambda xs: 0.0, n_bootstrap=0)

    def test_invalid_confidence_level_raises(self):
        with pytest.raises(ValueError, match="confidence_level"):
            bootstrap_ci([1.0], statistic=lambda xs: 0.0, confidence_level=1.5)

    def test_reproducible_with_seed(self):
        data = [float(i % 10) for i in range(100)]
        stat = lambda xs: sum(xs) / len(xs)
        lo1, hi1 = bootstrap_ci(data, stat, seed=42)
        lo2, hi2 = bootstrap_ci(data, stat, seed=42)
        assert lo1 == lo2 and hi1 == hi2

    def test_single_element(self):
        lo, hi = bootstrap_ci([3.14], statistic=lambda xs: xs[0], seed=0)
        assert lo == pytest.approx(3.14)
        assert hi == pytest.approx(3.14)

    def test_ci_width_shrinks_with_more_data(self):
        small_data = [float(i % 2) for i in range(10)]
        large_data = [float(i % 2) for i in range(200)]
        stat = lambda xs: sum(xs) / len(xs)
        lo_s, hi_s = bootstrap_ci(small_data, stat, seed=0)
        lo_l, hi_l = bootstrap_ci(large_data, stat, seed=0)
        assert (hi_l - lo_l) < (hi_s - lo_s)


# ---------------------------------------------------------------------------
# ablation_table
# ---------------------------------------------------------------------------


class TestAblationTable:
    def _make_records(self, version_outcomes: list[tuple[str, str]]) -> list[RunRecord]:
        return [
            RunRecord(
                feature_id=f"f{i}",
                feature_name=f"Feature {i}",
                outcome=outcome,
                confidence=None,
                version=version,
                duration_ms=None,
                cost_usd=None,
                num_turns=None,
            )
            for i, (version, outcome) in enumerate(version_outcomes)
        ]

    def test_returns_one_row_per_version(self):
        records = self._make_records([("V1", "completed"), ("V2", "failed")])
        rows = ablation_table(records, versions=["V1", "V2"])
        assert len(rows) == 2

    def test_row_types(self):
        records = self._make_records([("V1", "completed")])
        rows = ablation_table(records, versions=["V1"])
        assert all(isinstance(r, AblationRow) for r in rows)

    def test_success_rate_correct(self):
        records = self._make_records(
            [("V1", "completed"), ("V1", "completed"), ("V1", "failed")]
        )
        rows = ablation_table(records, versions=["V1"])
        assert rows[0].success_rate == pytest.approx(2 / 3)

    def test_empty_version_group(self):
        records = self._make_records([("V1", "completed")])
        rows = ablation_table(records, versions=["V0", "V1"])
        v0_row = next(r for r in rows if r.version == "V0")
        assert v0_row.n == 0
        assert v0_row.success_rate == 0.0
        assert v0_row.ci_lower is None

    def test_uses_version_labels_by_default(self):
        records = self._make_records([("V1", "completed")])
        rows = ablation_table(records)
        versions_in_table = [r.version for r in rows]
        assert versions_in_table == VERSION_LABELS

    def test_ci_none_for_single_record(self):
        records = self._make_records([("V1", "completed")])
        rows = ablation_table(records, versions=["V1"])
        assert rows[0].ci_lower is None
        assert rows[0].ci_upper is None

    def test_ci_set_for_multiple_records(self):
        records = self._make_records(
            [("V1", "completed")] * 5 + [("V1", "failed")] * 5
        )
        rows = ablation_table(records, versions=["V1"])
        assert rows[0].ci_lower is not None
        assert rows[0].ci_upper is not None
        assert rows[0].ci_lower <= rows[0].success_rate <= rows[0].ci_upper

    def test_mean_cost_computed(self):
        records = [
            RunRecord("a", "F", "completed", None, "V1", None, 1.0, None),
            RunRecord("b", "F", "failed", None, "V1", None, 3.0, None),
        ]
        rows = ablation_table(records, versions=["V1"])
        assert rows[0].mean_cost_usd == pytest.approx(2.0)

    def test_mean_turns_computed(self):
        records = [
            RunRecord("a", "F", "completed", None, "V1", None, None, 4),
            RunRecord("b", "F", "failed", None, "V1", None, None, 6),
        ]
        rows = ablation_table(records, versions=["V1"])
        assert rows[0].mean_turns == pytest.approx(5.0)

    def test_ece_computed_when_confidence_present(self):
        records = [
            RunRecord("a", "F", "completed", 0.9, "V1", None, None, None),
            RunRecord("b", "F", "failed", 0.9, "V1", None, None, None),
            RunRecord("c", "F", "completed", 0.9, "V1", None, None, None),
        ]
        rows = ablation_table(records, versions=["V1"])
        assert rows[0].ece is not None
        assert 0.0 <= rows[0].ece <= 1.0

    def test_ece_none_when_no_confidence(self):
        records = self._make_records([("V1", "completed")])
        rows = ablation_table(records, versions=["V1"])
        assert rows[0].ece is None

    def test_version_order_preserved(self):
        records = self._make_records(
            [("V-1", "completed"), ("V0", "failed"), ("V1", "completed")]
        )
        rows = ablation_table(records, versions=["V-1", "V0", "V1"])
        assert [r.version for r in rows] == ["V-1", "V0", "V1"]


# ---------------------------------------------------------------------------
# VERSION_LABELS
# ---------------------------------------------------------------------------


class TestVersionLabels:
    def test_has_five_labels(self):
        assert len(VERSION_LABELS) == 5

    def test_contains_expected_labels(self):
        for label in ("V-1", "V0", "V1", "V2", "V3"):
            assert label in VERSION_LABELS

    def test_ordered_from_negative_to_three(self):
        assert VERSION_LABELS == ["V-1", "V0", "V1", "V2", "V3"]
