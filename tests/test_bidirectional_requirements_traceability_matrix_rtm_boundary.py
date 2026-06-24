"""Boundary tests for spec_coverage RTM — empty, zero, or minimum input must
return a well-defined result rather than raising."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import pytest

from tools.spec_coverage import (
    check_halt_gate,
    compute_ac_record,
    compute_spec_coverage_pct,
    emit_rtm,
    flag_untraced_implementation,
    halt_gate_fires_at_80,
    handle_zero_acs,
    never_divides_by_zero_on_empty_acs,
)


# ── zero ACs ──────────────────────────────────────────────────────────────────


def test_compute_spec_coverage_pct_empty_acs_returns_zero(tmp_path):
    """Zero ACs → 0.0, no ZeroDivisionError."""
    result = compute_spec_coverage_pct([], [], tmp_path)
    assert result == 0.0


def test_handle_zero_acs_returns_zero():
    """handle_zero_acs([]) → 0.0, not an exception."""
    result = handle_zero_acs([])
    assert result == 0.0


def test_never_divides_by_zero_sentinel():
    """never_divides_by_zero_on_empty_acs() must return True."""
    assert never_divides_by_zero_on_empty_acs() is True


# ── empty test file list ───────────────────────────────────────────────────────


def test_compute_ac_record_no_test_files_returns_orphan(tmp_path):
    """No test files → AC is orphaned, not an exception."""
    ac = {"id": "AC-01", "text": "some function"}
    record = compute_ac_record(ac, [], tmp_path)
    assert record["orphan"] is True
    assert record["matched_tests"] == []
    assert record["exercised_files"] == []


def test_compute_spec_coverage_pct_no_test_files(tmp_path):
    """ACs exist but no test files → coverage is 0.0."""
    acs = [{"id": "AC-01", "text": "something"}, {"id": "AC-02", "text": "else"}]
    result = compute_spec_coverage_pct(acs, [], tmp_path)
    assert result == 0.0


# ── check_halt_gate boundary at exactly 0.80 ─────────────────────────────────


def test_halt_gate_exactly_at_threshold_passes():
    """spec_coverage_pct == 0.80 is exactly the threshold — must PASS."""
    passed, reason = check_halt_gate({"spec_coverage_pct": 0.80})
    assert passed is True
    assert reason == ""


def test_halt_gate_just_below_threshold_fails():
    """spec_coverage_pct = 0.7999... must FAIL."""
    passed, reason = check_halt_gate({"spec_coverage_pct": 0.7999})
    assert passed is False
    assert len(reason) > 0


# ── emit_rtm with minimal RTM dict ───────────────────────────────────────────


def test_emit_rtm_minimal_dict(tmp_path):
    """Minimal RTM dict (empty acs, empty untraced) must produce files without raising."""
    rtm = {
        "feature_id": "min-feature",
        "acs": {},
        "spec_coverage_pct": 1.0,
        "untraced_implementations": [],
    }
    json_path, html_path = emit_rtm(rtm, out_dir=tmp_path)
    assert json_path.exists()
    assert html_path.exists()


def test_emit_rtm_empty_untraced_html_says_none(tmp_path):
    """When untraced_implementations is empty, HTML should not list any rows."""
    rtm = {
        "feature_id": "no-untraced",
        "acs": {},
        "spec_coverage_pct": 1.0,
        "untraced_implementations": [],
    }
    _, html_path = emit_rtm(rtm, out_dir=tmp_path)
    content = html_path.read_text()
    assert "None" in content


# ── flag_untraced_implementation with no src functions ───────────────────────


def test_flag_untraced_empty_src(tmp_path):
    """Workspace with no src/ → returns empty list, not an exception."""
    (tmp_path / "tests").mkdir()
    result = flag_untraced_implementation(workspace=tmp_path, acs=[], test_files=[])
    assert result == []


# ── halt_gate_fires_at_80 boundary ───────────────────────────────────────────


def test_halt_gate_fires_at_80_zero_coverage():
    """Zero coverage → gate fires (True)."""
    assert halt_gate_fires_at_80(0.0) is True


def test_halt_gate_fires_at_80_full_coverage():
    """Full coverage → gate does not fire (False)."""
    assert halt_gate_fires_at_80(1.0) is False


def test_halt_gate_fires_at_80_exactly_threshold():
    """Exactly 0.80 → gate does not fire (False)."""
    assert halt_gate_fires_at_80(0.80) is False
