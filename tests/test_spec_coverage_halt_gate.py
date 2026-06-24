"""Tests for spec_coverage_pct halt-gate at 0.80."""

from __future__ import annotations

import pathlib

import pytest


def _make_workspace(tmp_path: pathlib.Path, num_acs: int, num_covered: int) -> pathlib.Path:
    """Create a workspace where exactly num_covered of num_acs have test matches."""
    lines = ["acceptance_criteria:\n"]
    for i in range(1, num_acs + 1):
        lines.append(f"  - id: AC-{i:02d}\n    text: 'Feature AC-{i:02d}'\n")
    (tmp_path / "spec.yaml").write_text("".join(lines))

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(exist_ok=True)
    # One test file referencing covered ACs
    ref_ids = " ".join(f"AC-{i:02d}" for i in range(1, num_covered + 1))
    (tests_dir / "test_covered.py").write_text(
        f"# {ref_ids}\ndef test_placeholder(): assert True\n"
    )
    return tmp_path


def test_halt_gate_passes_when_above_threshold(tmp_path):
    from tools.spec_coverage import build_rtm, check_halt_gate

    ws = _make_workspace(tmp_path, num_acs=5, num_covered=5)
    rtm = build_rtm(workspace=ws, feature_id="f1", spec_file=ws / "spec.yaml")

    passed, reason = check_halt_gate(rtm)
    assert passed is True
    assert reason == ""


def test_halt_gate_fails_when_below_threshold(tmp_path):
    from tools.spec_coverage import build_rtm, check_halt_gate

    # 3/5 = 0.60 < 0.80
    ws = _make_workspace(tmp_path, num_acs=5, num_covered=3)
    rtm = build_rtm(workspace=ws, feature_id="f2", spec_file=ws / "spec.yaml")

    passed, reason = check_halt_gate(rtm)
    assert passed is False
    assert "0.80" in reason or "80" in reason


def test_halt_gate_exactly_at_threshold_passes(tmp_path):
    from tools.spec_coverage import build_rtm, check_halt_gate

    # 4/5 = 0.80 — boundary is inclusive
    ws = _make_workspace(tmp_path, num_acs=5, num_covered=4)
    rtm = build_rtm(workspace=ws, feature_id="f3", spec_file=ws / "spec.yaml")

    passed, reason = check_halt_gate(rtm)
    assert passed is True


def test_spec_coverage_pct_written_to_metrics_yaml(tmp_path):
    import yaml  # type: ignore

    from tools.spec_coverage import build_rtm

    ws = _make_workspace(tmp_path, num_acs=4, num_covered=4)
    metrics_path = ws / "metrics.yaml"

    build_rtm(
        workspace=ws,
        feature_id="f-metrics",
        spec_file=ws / "spec.yaml",
        metrics_path=metrics_path,
    )

    assert metrics_path.exists(), "metrics.yaml was not created"
    data = yaml.safe_load(metrics_path.read_text())
    assert "spec_coverage_pct" in data
    assert abs(data["spec_coverage_pct"] - 1.0) < 0.01


def test_spec_coverage_pct_zero_acs_returns_one(tmp_path):
    """Edge case: no ACs → 100% coverage (nothing to cover)."""
    (tmp_path / "spec.yaml").write_text("acceptance_criteria: []\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()

    from tools.spec_coverage import build_rtm

    rtm = build_rtm(workspace=tmp_path, feature_id="f-empty", spec_file=tmp_path / "spec.yaml")
    assert rtm["spec_coverage_pct"] == 1.0


def test_halt_gate_reason_includes_coverage_pct(tmp_path):
    from tools.spec_coverage import build_rtm, check_halt_gate

    ws = _make_workspace(tmp_path, num_acs=10, num_covered=2)
    rtm = build_rtm(workspace=ws, feature_id="f-msg", spec_file=ws / "spec.yaml")

    passed, reason = check_halt_gate(rtm)
    assert not passed
    # Reason should mention the actual pct
    assert "0.2" in reason or "20" in reason
