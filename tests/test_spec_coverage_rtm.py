"""Tests for the bidirectional RTM generator in tools/spec_coverage.py.

Covers forward (AC -> test -> file) and backward (code-region -> AC)
traceability, the rtm.json / rtm.html artifacts, the spec_coverage_pct
metric, the 0.80 halt-gate, and the untraced_implementation flagging.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import pytest
import yaml

from tools.spec_coverage import (
    build_rtm,
    check_halt_gate,
    flag_untraced_implementation,
    generate_rtm,
)


# ── fixtures ──────────────────────────────────────────────────────────────────


def _make_workspace(tmp_path, *, acs, src_files=None, test_files=None):
    """Create a minimal workspace with spec.yaml, src/, and tests/."""
    spec = {"acceptance_criteria": acs}
    (tmp_path / "spec.yaml").write_text(yaml.safe_dump(spec))

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    for name, content in (src_files or {}).items():
        (src_dir / name).write_text(content)

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    for name, content in (test_files or {}).items():
        (tests_dir / name).write_text(content)

    return tmp_path


# ── forward traceability ──────────────────────────────────────────────────────


def test_covered_ac_is_not_orphan(tmp_path):
    """An AC referenced by a test is marked covered (not orphan)."""
    ws = _make_workspace(
        tmp_path,
        acs=[{"id": "AC-01", "text": "compute widget total"}],
        test_files={"test_widget.py": "def test_ac01():\n    # AC-01\n    assert True\n"},
    )
    rtm = generate_rtm(
        workspace=ws,
        feature_id="feat-fwd",
        spec_file=ws / "spec.yaml",
        runs_dir=ws / "runs",
        metrics_path=ws / "metrics.yaml",
        findings_path=ws / "reviews" / "findings.yaml",
    )
    assert rtm["acs"]["AC-01"]["orphan"] is False
    assert any(
        m.endswith("test_widget.py") for m in rtm["acs"]["AC-01"]["matched_tests"]
    )


def test_orphan_ac_has_no_matched_tests(tmp_path):
    """An AC with no referencing test is flagged as orphan."""
    ws = _make_workspace(
        tmp_path,
        acs=[{"id": "AC-99", "text": "zzzznevermatched requirement"}],
        test_files={"test_other.py": "def test_unrelated():\n    assert 1 == 1\n"},
    )
    rtm = generate_rtm(
        workspace=ws,
        feature_id="feat-orphan",
        spec_file=ws / "spec.yaml",
        runs_dir=ws / "runs",
        metrics_path=ws / "metrics.yaml",
        findings_path=ws / "reviews" / "findings.yaml",
    )
    assert rtm["acs"]["AC-99"]["orphan"] is True
    assert rtm["acs"]["AC-99"]["matched_tests"] == []


def test_spec_coverage_pct_is_covered_over_total(tmp_path):
    """spec_coverage_pct == covered_acs / total_acs."""
    ws = _make_workspace(
        tmp_path,
        acs=[
            {"id": "AC-01", "text": "alpha behaviour"},
            {"id": "AC-02", "text": "zzzuncoveredbeta"},
        ],
        test_files={"test_alpha.py": "def test_a():\n    # AC-01\n    assert True\n"},
    )
    rtm = generate_rtm(
        workspace=ws,
        feature_id="feat-pct",
        spec_file=ws / "spec.yaml",
        runs_dir=ws / "runs",
        metrics_path=ws / "metrics.yaml",
        findings_path=ws / "reviews" / "findings.yaml",
    )
    assert rtm["spec_coverage_pct"] == pytest.approx(0.5)


# ── artifacts ─────────────────────────────────────────────────────────────────


def test_generate_rtm_emits_json_and_html(tmp_path):
    """generate_rtm writes runs/<feature_id>/rtm.json and rtm.html."""
    ws = _make_workspace(
        tmp_path,
        acs=[{"id": "AC-01", "text": "something"}],
        test_files={"test_x.py": "# AC-01\ndef test_x():\n    assert True\n"},
    )
    feature_id = "feat-artifacts"
    generate_rtm(
        workspace=ws,
        feature_id=feature_id,
        spec_file=ws / "spec.yaml",
        runs_dir=ws / "runs",
        metrics_path=ws / "metrics.yaml",
        findings_path=ws / "reviews" / "findings.yaml",
    )
    json_path = ws / "runs" / feature_id / "rtm.json"
    html_path = ws / "runs" / feature_id / "rtm.html"
    assert json_path.is_file()
    assert html_path.is_file()

    data = json.loads(json_path.read_text())
    assert data["feature_id"] == feature_id
    assert "acs" in data
    assert "<table" in html_path.read_text()


def test_metrics_yaml_records_spec_coverage_pct(tmp_path):
    """metrics.yaml gets a spec_coverage_pct field."""
    ws = _make_workspace(
        tmp_path,
        acs=[{"id": "AC-01", "text": "thing"}],
        test_files={"test_t.py": "# AC-01\ndef test_t():\n    assert True\n"},
    )
    metrics_path = ws / "metrics.yaml"
    rtm = generate_rtm(
        workspace=ws,
        feature_id="feat-metrics",
        spec_file=ws / "spec.yaml",
        runs_dir=ws / "runs",
        metrics_path=metrics_path,
        findings_path=ws / "reviews" / "findings.yaml",
    )
    metrics = yaml.safe_load(metrics_path.read_text())
    assert metrics["spec_coverage_pct"] == rtm["spec_coverage_pct"]


# ── backward traceability / untraced implementation ───────────────────────────


def test_flag_untraced_implementation_flags_unlinked_function(tmp_path):
    """A public src function with no AC/test link is flagged untraced."""
    ws = _make_workspace(
        tmp_path,
        acs=[{"id": "AC-01", "text": "unrelated requirement"}],
        src_files={"mod.py": "def orphan_fn():\n    return 1\n"},
        test_files={"test_nothing.py": "def test_z():\n    assert True\n"},
    )
    untraced = flag_untraced_implementation(
        workspace=ws,
        acs=[{"id": "AC-01", "text": "unrelated requirement"}],
    )
    names = {fn["function"] for fn in untraced}
    assert "orphan_fn" in names


def test_traced_function_is_not_flagged(tmp_path):
    """A function referenced by a test is not flagged untraced."""
    ws = _make_workspace(
        tmp_path,
        acs=[{"id": "AC-01", "text": "req"}],
        src_files={"mod.py": "def linked_fn():\n    return 1\n"},
        test_files={"test_linked.py": "def test_l():\n    linked_fn()\n"},
    )
    untraced = flag_untraced_implementation(
        workspace=ws,
        acs=[{"id": "AC-01", "text": "req"}],
    )
    names = {fn["function"] for fn in untraced}
    assert "linked_fn" not in names


def test_untraced_written_to_findings(tmp_path):
    """Untraced functions produce untraced_implementation findings."""
    ws = _make_workspace(
        tmp_path,
        acs=[{"id": "AC-01", "text": "unrelated"}],
        src_files={"mod.py": "def loose_fn():\n    return 1\n"},
        test_files={"test_nothing.py": "def test_z():\n    assert True\n"},
    )
    findings_path = ws / "reviews" / "findings.yaml"
    generate_rtm(
        workspace=ws,
        feature_id="feat-find",
        spec_file=ws / "spec.yaml",
        runs_dir=ws / "runs",
        metrics_path=ws / "metrics.yaml",
        findings_path=findings_path,
    )
    findings = yaml.safe_load(findings_path.read_text())["findings"]
    tags = {tag for f in findings for tag in f.get("tags", [])}
    assert "untraced_implementation" in tags


# ── halt gate ─────────────────────────────────────────────────────────────────


def test_halt_gate_fails_below_threshold():
    """spec_coverage_pct < 0.80 → halt gate fails."""
    passed, reason = check_halt_gate({"spec_coverage_pct": 0.5})
    assert passed is False
    assert "0.80" in reason


def test_halt_gate_passes_at_threshold():
    """spec_coverage_pct == 0.80 → halt gate passes."""
    passed, reason = check_halt_gate({"spec_coverage_pct": 0.80})
    assert passed is True
    assert reason == ""


def test_build_rtm_and_generate_rtm_agree(tmp_path):
    """generate_rtm is a faithful alias of build_rtm."""
    ws = _make_workspace(
        tmp_path,
        acs=[{"id": "AC-01", "text": "req"}],
        test_files={"test_x.py": "# AC-01\ndef test_x():\n    assert True\n"},
    )
    kwargs = dict(
        workspace=ws,
        feature_id="feat-agree",
        spec_file=ws / "spec.yaml",
        runs_dir=ws / "runs",
        metrics_path=ws / "metrics.yaml",
        findings_path=ws / "reviews" / "findings.yaml",
    )
    a = build_rtm(**kwargs)
    b = generate_rtm(**kwargs)
    assert a["spec_coverage_pct"] == b["spec_coverage_pct"]
    assert a["acs"].keys() == b["acs"].keys()
