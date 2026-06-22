"""Boundary tests for spec_critic.registry (F-R7-450).

Verifies that empty, zero, or minimum input returns a well-defined result
rather than raising (boundary cases).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spec_critic.registry import write_findings, detect_regression, compute_critic_repeat_rate


def test_write_findings_with_empty_strings(tmp_path):
    """Empty string arguments are accepted and return a valid dict."""
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    result = write_findings(
        spec_hash="",
        slot_id="",
        defect_type="",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    assert isinstance(result, dict)
    assert result["is_regression"] is False
    assert result["occurrence_count"] == 1


def test_detect_regression_on_missing_file_returns_false(tmp_path):
    """detect_regression returns False when the findings file does not exist."""
    missing_path = tmp_path / "nonexistent_spec_findings.yaml"

    result = detect_regression(
        spec_hash="abc123",
        slot_id="AC-0",
        defect_type="ambiguity",
        findings_path=missing_path,
    )

    assert result is False


def test_detect_regression_on_unknown_key_returns_false(tmp_path):
    """detect_regression returns False for a key that was never recorded."""
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    write_findings(
        spec_hash="known_hash",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="run-1",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    result = detect_regression(
        spec_hash="unknown_hash",
        slot_id="AC-0",
        defect_type="ambiguity",
        findings_path=findings_path,
    )

    assert result is False


def test_compute_critic_repeat_rate_on_empty_registry(tmp_path):
    """compute_critic_repeat_rate returns 0.0 on an empty registry."""
    missing_path = tmp_path / "nonexistent.yaml"

    rate = compute_critic_repeat_rate(findings_path=missing_path)

    assert rate == 0.0


def test_write_findings_minimal_args(tmp_path):
    """write_findings works with only the three required positional arguments."""
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    result = write_findings(
        spec_hash="min001",
        slot_id="AC-0",
        defect_type="ambiguity",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    assert isinstance(result, dict)
    assert result["occurrence_count"] == 1
    assert findings_path.exists()


def test_write_findings_severity_default_is_warning(tmp_path):
    """Default severity is 'warning' when not specified."""
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    result = write_findings(
        spec_hash="sev001",
        slot_id="AC-0",
        defect_type="ambiguity",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    assert result["severity"] == "warning"


def test_severity_stays_at_critical_when_already_max(tmp_path):
    """Severity does not escalate beyond 'critical'."""
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    for i in range(1, 6):
        r = write_findings(
            spec_hash="cap001",
            slot_id="AC-0",
            defect_type="ambiguity",
            severity="critical",
            run_id=f"run-{i}",
            findings_path=findings_path,
            metrics_path=metrics_path,
        )

    assert r["severity"] == "critical"


def test_single_run_repeat_rate_is_zero(tmp_path):
    """A single recording yields repeat rate of 0.0 (no regression possible)."""
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    write_findings(
        spec_hash="single001",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="only-run",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    rate = compute_critic_repeat_rate(findings_path=findings_path)
    assert rate == 0.0
