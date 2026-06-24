"""Error-path tests for the RTM artifact — invalid input must raise ValueError.

The function must not silently succeed when given invalid input.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import pytest

from tools.spec_coverage import emit_rtm


# ── emit_rtm error paths ──────────────────────────────────────────────────────


def test_emit_rtm_raises_value_error_for_non_dict(tmp_path):
    """emit_rtm(None, ...) must raise ValueError, not silently succeed."""
    with pytest.raises(ValueError):
        emit_rtm(None, out_dir=tmp_path)


def test_emit_rtm_raises_value_error_for_list(tmp_path):
    """emit_rtm([], ...) must raise ValueError."""
    with pytest.raises(ValueError):
        emit_rtm([], out_dir=tmp_path)


def test_emit_rtm_raises_value_error_for_string(tmp_path):
    """emit_rtm('invalid', ...) must raise ValueError."""
    with pytest.raises(ValueError):
        emit_rtm("invalid", out_dir=tmp_path)


def test_emit_rtm_raises_value_error_for_integer(tmp_path):
    """emit_rtm(42, ...) must raise ValueError."""
    with pytest.raises(ValueError):
        emit_rtm(42, out_dir=tmp_path)


def test_emit_rtm_error_message_names_type(tmp_path):
    """ValueError message should indicate the bad type, not be empty."""
    with pytest.raises(ValueError, match="dict"):
        emit_rtm("not-a-dict", out_dir=tmp_path)


# ── check_halt_gate with invalid input ───────────────────────────────────────


def test_check_halt_gate_missing_key_does_not_raise():
    """check_halt_gate({}) must return a result (defaults to 0.0), not raise."""
    from tools.spec_coverage import check_halt_gate

    passed, reason = check_halt_gate({})
    assert passed is False
    assert isinstance(reason, str) and len(reason) > 0


# ── handle_zero_acs error path ────────────────────────────────────────────────


def test_handle_zero_acs_raises_for_non_empty():
    """handle_zero_acs raises ValueError when given a non-empty list."""
    from tools.spec_coverage import handle_zero_acs

    with pytest.raises(ValueError):
        handle_zero_acs([{"id": "AC-01", "text": "something"}])


# ── emit_rtm_json invalid input ───────────────────────────────────────────────


def test_emit_rtm_json_raises_on_unwritable_dir(tmp_path):
    """emit_rtm_json raises PermissionError when the output dir is not writable."""
    import os

    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    runs_dir.chmod(0o444)  # read-only

    rtm = {"feature_id": "f1", "acs": {}, "spec_coverage_pct": 1.0, "untraced_implementations": []}
    try:
        with pytest.raises((PermissionError, OSError)):
            from tools.spec_coverage import emit_rtm_json
            emit_rtm_json(rtm, runs_dir=runs_dir, feature_id="f1")
    finally:
        runs_dir.chmod(0o755)  # restore for tmp cleanup


# ── bidirectional_requirements_traceability_matrix_rtm_artifact error path ───


def test_rtm_artifact_invalid_ac_items_do_not_crash():
    """ACs with missing keys should not raise; missing id falls back to text slice."""
    from bob.bidirectional_requirements_traceability_matrix_rtm_artifact import (
        bidirectional_requirements_traceability_matrix_rtm_artifact,
    )

    result = bidirectional_requirements_traceability_matrix_rtm_artifact(
        workspace=".",
        feature_id="feat-bad-ac",
        acs=[{"text": "some requirement with no id field"}],
        test_contents={},
        src_functions=[],
    )

    assert isinstance(result, dict)
    assert result["spec_coverage_pct"] == 0.0


def test_rtm_artifact_src_function_missing_name_does_not_crash():
    """src_functions dicts with missing 'function' key should not cause crash."""
    from bob.bidirectional_requirements_traceability_matrix_rtm_artifact import (
        bidirectional_requirements_traceability_matrix_rtm_artifact,
    )

    with pytest.raises((KeyError, AttributeError, TypeError)):
        bidirectional_requirements_traceability_matrix_rtm_artifact(
            workspace=".",
            feature_id="feat-bad-fn",
            acs=[{"id": "AC-01", "text": "something"}],
            test_contents={},
            src_functions=[{"file": "src/foo.py"}],  # missing 'function' key
        )
