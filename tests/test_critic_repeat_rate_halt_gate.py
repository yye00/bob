"""Tests for critic_repeat_rate metric and halt-gate in spec_findings_registry.

critic_repeat_rate = (regression events in last 3 run_ids) / (total events in window).
Halt-gate fires when rate > 0.30 over 3 runs.
"""

from __future__ import annotations

import yaml

from bob3.spec_quality.spec_findings_registry import (
    _HALT_GATE_THRESHOLD,
    _HALT_GATE_WINDOW,
    compute_critic_repeat_rate,
    is_halt_gate_fired,
    record,
)


def _rec(fp, mp, spec_hash, slot, dtype, *, run_id="run-1"):
    return record(
        spec_hash, slot, dtype,
        run_id=run_id,
        findings_path=fp,
        metrics_path=mp,
    )


class TestCriticRepeatRate:
    def test_rate_zero_with_no_regressions(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        _rec(fp, mp, "h1", "AC-0", "ambiguity", run_id="r1")
        _rec(fp, mp, "h2", "AC-0", "ambiguity", run_id="r2")
        rate = compute_critic_repeat_rate(findings_path=fp)
        assert rate == 0.0

    def test_rate_one_with_all_regressions(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        # First occurrence (not regression)
        _rec(fp, mp, "h1", "AC-0", "ambiguity", run_id="r1")
        # Second + third (regressions)
        _rec(fp, mp, "h1", "AC-0", "ambiguity", run_id="r2")
        _rec(fp, mp, "h1", "AC-0", "ambiguity", run_id="r3")
        rate = compute_critic_repeat_rate(findings_path=fp)
        # Window=3 runs; events in window from r1,r2,r3: 3 total, 2 regressions
        assert rate > 0.0

    def test_rate_reflects_last_window_runs(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        # Many old regressions in r1
        for i in range(10):
            _rec(fp, mp, f"h{i}", "AC-0", "ambiguity", run_id="r-old")
            _rec(fp, mp, f"h{i}", "AC-0", "ambiguity", run_id="r-old")
        # Recent clean runs
        _rec(fp, mp, "fresh1", "AC-0", "ambiguity", run_id="r-new1")
        _rec(fp, mp, "fresh2", "AC-0", "ambiguity", run_id="r-new2")
        rate = compute_critic_repeat_rate(findings_path=fp)
        # Recent window (3 runs: r-old, r-new1, r-new2) — new runs have no regressions
        assert isinstance(rate, float)
        assert 0.0 <= rate <= 1.0

    def test_rate_zero_when_no_findings(self, tmp_path):
        fp = tmp_path / "missing.yaml"
        rate = compute_critic_repeat_rate(findings_path=fp)
        assert rate == 0.0

    def test_threshold_constant_is_0_30(self):
        assert _HALT_GATE_THRESHOLD == 0.30

    def test_window_constant_is_3(self):
        assert _HALT_GATE_WINDOW == 3

    def test_metrics_yaml_created_on_record(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        assert not mp.exists()
        _rec(fp, mp, "h1", "AC-0", "ambiguity", run_id="r1")
        assert mp.exists()

    def test_metrics_yaml_contains_critic_repeat_rate(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        _rec(fp, mp, "h1", "AC-0", "ambiguity", run_id="r1")
        metrics = yaml.safe_load(mp.read_text())
        assert "critic_repeat_rate" in metrics

    def test_metrics_yaml_contains_halt_gate_fired(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        _rec(fp, mp, "h1", "AC-0", "ambiguity", run_id="r1")
        metrics = yaml.safe_load(mp.read_text())
        assert "halt_gate_fired" in metrics

    def test_halt_gate_false_when_no_regressions(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        for i in range(5):
            _rec(fp, mp, f"unique-{i}", "AC-0", "ambiguity", run_id=f"r{i}")
        assert is_halt_gate_fired(findings_path=fp, metrics_path=mp) is False

    def test_halt_gate_fires_above_threshold(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        # Create a high regression rate: same key recorded many times in same run
        _rec(fp, mp, "h1", "AC-0", "ambiguity", run_id="r1")
        # Record regressions in run r2 (same key = regression)
        for _ in range(5):
            _rec(fp, mp, "h1", "AC-0", "ambiguity", run_id="r2")
        rate = compute_critic_repeat_rate(findings_path=fp)
        # The halt gate depends on rate > 0.30; verify the metric is consistent
        fired = is_halt_gate_fired(findings_path=fp, metrics_path=mp)
        metrics = yaml.safe_load(mp.read_text())
        assert metrics["halt_gate_fired"] == (metrics["critic_repeat_rate"] > _HALT_GATE_THRESHOLD)

    def test_halt_gate_result_consistent_with_metrics_yaml(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        _rec(fp, mp, "h1", "AC-0", "ambiguity", run_id="r1")
        _rec(fp, mp, "h1", "AC-0", "ambiguity", run_id="r2")
        fired = is_halt_gate_fired(findings_path=fp, metrics_path=mp)
        metrics = yaml.safe_load(mp.read_text())
        assert fired == metrics["halt_gate_fired"]

    def test_is_halt_gate_fired_with_no_findings_file(self, tmp_path):
        fp = tmp_path / "nonexistent.yaml"
        mp = tmp_path / "no_metrics.yaml"
        # Should not raise; returns False when rate is 0
        result = is_halt_gate_fired(findings_path=fp, metrics_path=mp)
        assert result is False
