"""Tests for BF-5 — Resurrection gate (Tier-1 partial-work detector).

Acceptance criteria tested:
  - Function defined: bob3.bf_5_resurrection_gate_tier_1_partial_work_detector
  - behavior: BF-5 handles empty/zero input by returning well-defined result (no crash)
  - behavior: BF-5 raises ValueError (or returns rejection) for invalid input
  - File exists: src/bob3/brownfield/resurrection.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.bf_5_resurrection_gate_tier_1_partial_work_detector import (
    bf_5_resurrection_gate_tier_1_partial_work_detector,
)


def test_bf_5_resurrection_gate_tier_1_partial_work_detector():
    """Primary AC test: function exists and returns correct structure on empty input."""
    result = bf_5_resurrection_gate_tier_1_partial_work_detector()
    assert isinstance(result, dict)
    assert "signals_fired" in result
    assert "should_demote" in result
    assert result["signals_fired"] == []
    assert result["should_demote"] is False


def test_empty_touches_returns_no_signals():
    """Empty touches list (zero input) returns no signals, no crash."""
    result = bf_5_resurrection_gate_tier_1_partial_work_detector(
        workspace_root=".",
        touches=[],
        feature_keywords=[],
    )
    assert isinstance(result, dict)
    assert result["signals_fired"] == []
    assert result["should_demote"] is False


def test_none_touches_returns_no_signals():
    """None touches (boundary case) returns well-defined result, no crash."""
    result = bf_5_resurrection_gate_tier_1_partial_work_detector(
        workspace_root=".",
        touches=None,
        feature_keywords=[],
    )
    assert isinstance(result, dict)
    assert result["signals_fired"] == []
    assert result["should_demote"] is False


def test_invalid_touches_raises_value_error():
    """Non-list touches (not None, not list) raises ValueError."""
    with pytest.raises(ValueError):
        bf_5_resurrection_gate_tier_1_partial_work_detector(
            workspace_root=".",
            touches="not-a-list",
            feature_keywords=[],
        )


def test_invalid_feature_keywords_raises_value_error():
    """Non-list feature_keywords raises ValueError."""
    with pytest.raises(ValueError):
        bf_5_resurrection_gate_tier_1_partial_work_detector(
            workspace_root=".",
            touches=[],
            feature_keywords="not-a-list",
        )


def test_result_has_required_keys():
    """Result dict always contains signals_fired, should_demote, report_path."""
    result = bf_5_resurrection_gate_tier_1_partial_work_detector()
    required_keys = {"signals_fired", "should_demote", "report_path"}
    assert required_keys.issubset(result.keys()), (
        f"Missing keys: {required_keys - result.keys()}"
    )


def test_report_path_none_when_no_signals():
    """report_path is None when no signals fire (no report written)."""
    result = bf_5_resurrection_gate_tier_1_partial_work_detector(
        workspace_root=".",
        touches=[],
        feature_keywords=[],
    )
    assert result["report_path"] is None


def test_resurrection_module_exists():
    """File exists: src/bob3/brownfield/resurrection.py."""
    path = Path("src/bob3/brownfield/resurrection.py")
    assert path.exists(), f"Expected {path} to exist"


def test_signals_fired_is_list():
    """signals_fired is always a list."""
    result = bf_5_resurrection_gate_tier_1_partial_work_detector()
    assert isinstance(result["signals_fired"], list)


def test_with_nonexistent_workspace_returns_empty():
    """Nonexistent workspace root does not crash; returns empty signals."""
    result = bf_5_resurrection_gate_tier_1_partial_work_detector(
        workspace_root="/tmp/nonexistent_workspace_xyz_123",
        touches=["some/path.py"],
        feature_keywords=["keyword"],
    )
    assert isinstance(result, dict)
    assert result["signals_fired"] == []
    assert result["should_demote"] is False


def test_with_valid_workspace_no_signals(tmp_path):
    """Real workspace with no stale branches/todos returns no signals."""
    # Create a dummy file with no TODOs
    (tmp_path / "module.py").write_text("def hello(): return 42\n")
    result = bf_5_resurrection_gate_tier_1_partial_work_detector(
        workspace_root=str(tmp_path),
        touches=["module.py"],
        feature_keywords=["hello"],
    )
    assert isinstance(result, dict)
    assert isinstance(result["signals_fired"], list)
    assert result["should_demote"] is False


def test_todo_cluster_detected(tmp_path):
    """Signal C fires when file in touches has >= 3 TODO/FIXME comments."""
    content = "\n".join([
        "# TODO: fix this",
        "# TODO: handle edge case",
        "# FIXME: broken",
        "def placeholder(): pass",
    ])
    (tmp_path / "messy.py").write_text(content)
    result = bf_5_resurrection_gate_tier_1_partial_work_detector(
        workspace_root=str(tmp_path),
        touches=["messy.py"],
        feature_keywords=[],
        include_deep_signals=True,
    )
    assert isinstance(result, dict)
    assert any(s["signal_kind"] == "todo_cluster" for s in result["signals_fired"])
    assert result["should_demote"] is True
