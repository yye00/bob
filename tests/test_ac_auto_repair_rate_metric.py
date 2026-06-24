"""Tests for compute_auto_repair_rate (last-5-run average from metrics.yaml)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import yaml

from bob.spec_quality.ac_auto_repair import compute_auto_repair_rate


class TestComputeAutoRepairRate:
    """compute_auto_repair_rate returns the average repair rate over the last 5 runs."""

    def test_returns_zero_when_no_metrics_file(self, tmp_path: Path) -> None:
        fake_metrics = tmp_path / "metrics.yaml"
        with patch("bob.spec_quality.ac_auto_repair._METRICS_PATH", fake_metrics):
            assert compute_auto_repair_rate() == 0.0

    def test_returns_zero_when_history_empty(self, tmp_path: Path) -> None:
        fake_metrics = tmp_path / "metrics.yaml"
        fake_metrics.write_text(yaml.dump({"auto_repair_history": []}))
        with patch("bob.spec_quality.ac_auto_repair._METRICS_PATH", fake_metrics):
            assert compute_auto_repair_rate() == 0.0

    def test_single_run_rate(self, tmp_path: Path) -> None:
        fake_metrics = tmp_path / "metrics.yaml"
        fake_metrics.write_text(yaml.dump({
            "auto_repair_history": [{"timestamp": "2026-01-01T00:00:00Z", "rate": 0.75}]
        }))
        with patch("bob.spec_quality.ac_auto_repair._METRICS_PATH", fake_metrics):
            assert compute_auto_repair_rate() == 0.75

    def test_averages_last_five_runs(self, tmp_path: Path) -> None:
        fake_metrics = tmp_path / "metrics.yaml"
        history = [
            {"timestamp": f"2026-01-0{i}T00:00:00Z", "rate": rate}
            for i, rate in enumerate([0.2, 0.4, 0.6, 0.8, 1.0], start=1)
        ]
        fake_metrics.write_text(yaml.dump({"auto_repair_history": history}))
        with patch("bob.spec_quality.ac_auto_repair._METRICS_PATH", fake_metrics):
            result = compute_auto_repair_rate()
        assert abs(result - 0.6) < 1e-4

    def test_uses_only_last_five_when_more_exist(self, tmp_path: Path) -> None:
        fake_metrics = tmp_path / "metrics.yaml"
        # 7 runs; last 5 all have rate=1.0, earlier 2 have rate=0.0
        history = [
            {"timestamp": f"2026-01-0{i}T00:00:00Z", "rate": 0.0}
            for i in range(1, 3)
        ] + [
            {"timestamp": f"2026-01-1{i}T00:00:00Z", "rate": 1.0}
            for i in range(1, 6)
        ]
        fake_metrics.write_text(yaml.dump({"auto_repair_history": history}))
        with patch("bob.spec_quality.ac_auto_repair._METRICS_PATH", fake_metrics):
            result = compute_auto_repair_rate()
        assert result == 1.0

    def test_returns_zero_on_corrupt_yaml(self, tmp_path: Path) -> None:
        fake_metrics = tmp_path / "metrics.yaml"
        fake_metrics.write_text("not: valid: yaml: [[[")
        with patch("bob.spec_quality.ac_auto_repair._METRICS_PATH", fake_metrics):
            # Should not raise; corrupt data returns 0.0
            result = compute_auto_repair_rate()
        assert result == 0.0
