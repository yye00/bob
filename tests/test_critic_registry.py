"""Tests for bob.critic.registry — Persistent spec-critic findings registry (F-R7-450).

Covers write_finding, detect_regression, compute_critic_repeat_rate,
and halt-gate behaviour.
"""

from __future__ import annotations

import pytest

from bob.critic.registry import (
    write_finding,
    detect_regression,
    compute_critic_repeat_rate,
    is_halt_gate_fired,
)


# ---------------------------------------------------------------------------
# write_finding
# ---------------------------------------------------------------------------


def test_write_finding_returns_dict(tmp_path):
    """write_finding returns a dict with expected keys."""
    fp = tmp_path / "spec_findings.yaml"
    mp = tmp_path / "metrics.yaml"

    result = write_finding(
        spec_hash="abc123",
        slot_id="AC-0",
        defect_type="ambiguity",
        findings_path=fp,
        metrics_path=mp,
    )

    assert isinstance(result, dict)
    assert result["spec_hash"] == "abc123"
    assert result["slot_id"] == "AC-0"
    assert result["defect_type"] == "ambiguity"
    assert result["occurrence_count"] == 1
    assert result["is_regression"] is False


def test_write_finding_creates_yaml_file(tmp_path):
    """write_finding creates the YAML file on disk."""
    fp = tmp_path / "spec_findings.yaml"
    mp = tmp_path / "metrics.yaml"

    write_finding(
        spec_hash="abc123",
        slot_id="AC-0",
        defect_type="ambiguity",
        findings_path=fp,
        metrics_path=mp,
    )

    assert fp.exists()


def test_write_finding_second_call_flags_regression(tmp_path):
    """A second write_finding with the same key flags REGRESSION and escalates severity."""
    fp = tmp_path / "spec_findings.yaml"
    mp = tmp_path / "metrics.yaml"

    write_finding(
        spec_hash="sha1",
        slot_id="AC-0",
        defect_type="ambiguity",
        severity="warning",
        run_id="run-1",
        findings_path=fp,
        metrics_path=mp,
    )
    result2 = write_finding(
        spec_hash="sha1",
        slot_id="AC-0",
        defect_type="ambiguity",
        severity="warning",
        run_id="run-2",
        findings_path=fp,
        metrics_path=mp,
    )

    assert result2["is_regression"] is True
    assert result2["occurrence_count"] == 2
    # Severity should be escalated from 'warning' to 'error'
    assert result2["severity"] == "error"


def test_write_finding_different_keys_do_not_share_state(tmp_path):
    """Different (spec_hash, slot_id, defect_type) combinations are independent."""
    fp = tmp_path / "spec_findings.yaml"
    mp = tmp_path / "metrics.yaml"

    write_finding(
        spec_hash="h1",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="run-1",
        findings_path=fp,
        metrics_path=mp,
    )
    result = write_finding(
        spec_hash="h2",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="run-1",
        findings_path=fp,
        metrics_path=mp,
    )

    assert result["is_regression"] is False
    assert result["occurrence_count"] == 1


def test_write_finding_raises_on_invalid_severity(tmp_path):
    """write_finding raises ValueError for an unrecognised severity level."""
    fp = tmp_path / "spec_findings.yaml"
    mp = tmp_path / "metrics.yaml"

    with pytest.raises((ValueError, Exception)):
        write_finding(
            spec_hash="x",
            slot_id="AC-0",
            defect_type="ambiguity",
            severity="bogus",
            findings_path=fp,
            metrics_path=mp,
        )


def test_write_finding_raises_on_none_spec_hash(tmp_path):
    """write_finding raises on None spec_hash."""
    fp = tmp_path / "spec_findings.yaml"
    mp = tmp_path / "metrics.yaml"

    with pytest.raises((TypeError, ValueError, AttributeError)):
        write_finding(
            spec_hash=None,  # type: ignore[arg-type]
            slot_id="AC-0",
            defect_type="ambiguity",
            findings_path=fp,
            metrics_path=mp,
        )


# ---------------------------------------------------------------------------
# detect_regression
# ---------------------------------------------------------------------------


def test_detect_regression_false_on_first_write(tmp_path):
    """detect_regression returns False after only one write (not yet a regression)."""
    fp = tmp_path / "spec_findings.yaml"
    mp = tmp_path / "metrics.yaml"

    write_finding(
        spec_hash="r1",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="run-1",
        findings_path=fp,
        metrics_path=mp,
    )

    assert detect_regression("r1", "AC-0", "ambiguity", findings_path=fp) is False


def test_detect_regression_true_after_second_write(tmp_path):
    """detect_regression returns True after two writes with the same key."""
    fp = tmp_path / "spec_findings.yaml"
    mp = tmp_path / "metrics.yaml"

    write_finding(
        spec_hash="r2",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="run-1",
        findings_path=fp,
        metrics_path=mp,
    )
    write_finding(
        spec_hash="r2",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="run-2",
        findings_path=fp,
        metrics_path=mp,
    )

    assert detect_regression("r2", "AC-0", "ambiguity", findings_path=fp) is True


def test_detect_regression_false_on_missing_file(tmp_path):
    """detect_regression returns False when the findings file does not exist."""
    missing = tmp_path / "nonexistent.yaml"
    assert detect_regression("x", "AC-0", "ambiguity", findings_path=missing) is False


def test_detect_regression_raises_on_none_key(tmp_path):
    """detect_regression raises when a key argument is None."""
    fp = tmp_path / "spec_findings.yaml"

    with pytest.raises((TypeError, ValueError, AttributeError)):
        detect_regression(None, "AC-0", "ambiguity", findings_path=fp)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# compute_critic_repeat_rate
# ---------------------------------------------------------------------------


def test_compute_critic_repeat_rate_zero_on_empty(tmp_path):
    """compute_critic_repeat_rate returns 0.0 when the registry is empty."""
    missing = tmp_path / "nonexistent.yaml"
    assert compute_critic_repeat_rate(findings_path=missing) == 0.0


def test_compute_critic_repeat_rate_nonzero_after_regressions(tmp_path):
    """compute_critic_repeat_rate is > 0 after repeated findings across runs."""
    fp = tmp_path / "spec_findings.yaml"
    mp = tmp_path / "metrics.yaml"

    # run-1: new finding
    write_finding(
        spec_hash="h1",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="run-1",
        findings_path=fp,
        metrics_path=mp,
    )
    # run-2: same finding → regression
    write_finding(
        spec_hash="h1",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="run-2",
        findings_path=fp,
        metrics_path=mp,
    )
    # run-3: same finding → regression again
    write_finding(
        spec_hash="h1",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="run-3",
        findings_path=fp,
        metrics_path=mp,
    )

    rate = compute_critic_repeat_rate(findings_path=fp)
    assert rate > 0.0


# ---------------------------------------------------------------------------
# Halt-gate
# ---------------------------------------------------------------------------


def test_halt_gate_fires_when_rate_exceeds_threshold(tmp_path):
    """Halt-gate fires when critic_repeat_rate > 0.30 over 3 runs."""
    fp = tmp_path / "spec_findings.yaml"
    mp = tmp_path / "metrics.yaml"

    # Produce a repeat rate > 0.30: one unique entry per run-1, then repeat same entry
    # across run-2 and run-3 (so 2/3 window entries are regressions → 0.67 > 0.30)
    write_finding(
        spec_hash="h1",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="run-1",
        findings_path=fp,
        metrics_path=mp,
    )
    write_finding(
        spec_hash="h1",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="run-2",
        findings_path=fp,
        metrics_path=mp,
    )
    write_finding(
        spec_hash="h1",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="run-3",
        findings_path=fp,
        metrics_path=mp,
    )

    assert is_halt_gate_fired(findings_path=fp, metrics_path=mp) is True


def test_halt_gate_does_not_fire_on_clean_runs(tmp_path):
    """Halt-gate does not fire when repeat rate is below the threshold."""
    fp = tmp_path / "spec_findings.yaml"
    mp = tmp_path / "metrics.yaml"

    # All unique findings, no regressions → rate == 0.0
    for i in range(3):
        write_finding(
            spec_hash=f"unique-{i}",
            slot_id=f"AC-{i}",
            defect_type="ambiguity",
            run_id=f"run-{i}",
            findings_path=fp,
            metrics_path=mp,
        )

    assert is_halt_gate_fired(findings_path=fp, metrics_path=mp) is False
