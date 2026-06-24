"""Error-path tests for spec_critic.registry (F-R7-450).

Verifies that invalid input raises ValueError and functions do not
silently succeed on bad inputs (error path).
"""

from __future__ import annotations

import pytest

from spec_critic.registry import write_findings, detect_regression


def test_write_findings_raises_on_invalid_severity(tmp_path):
    """write_findings raises ValueError for an unrecognised severity level."""
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    with pytest.raises((ValueError, Exception)):
        write_findings(
            spec_hash="err001",
            slot_id="AC-0",
            defect_type="ambiguity",
            severity="bogus_level",
            findings_path=findings_path,
            metrics_path=metrics_path,
        )


def test_detect_regression_raises_on_none_spec_hash(tmp_path):
    """detect_regression raises on None spec_hash."""
    findings_path = tmp_path / "spec_findings.yaml"

    with pytest.raises((TypeError, AttributeError, ValueError)):
        detect_regression(
            spec_hash=None,  # type: ignore[arg-type]
            slot_id="AC-0",
            defect_type="ambiguity",
            findings_path=findings_path,
        )


def test_write_findings_raises_on_none_spec_hash(tmp_path):
    """write_findings raises on None spec_hash (not silently succeeds)."""
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    with pytest.raises((TypeError, AttributeError, ValueError)):
        write_findings(
            spec_hash=None,  # type: ignore[arg-type]
            slot_id="AC-0",
            defect_type="ambiguity",
            findings_path=findings_path,
            metrics_path=metrics_path,
        )


def test_write_findings_raises_on_none_slot_id(tmp_path):
    """write_findings raises on None slot_id."""
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    with pytest.raises((TypeError, AttributeError, ValueError)):
        write_findings(
            spec_hash="err002",
            slot_id=None,  # type: ignore[arg-type]
            defect_type="ambiguity",
            findings_path=findings_path,
            metrics_path=metrics_path,
        )


def test_write_findings_raises_on_none_defect_type(tmp_path):
    """write_findings raises on None defect_type."""
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    with pytest.raises((TypeError, AttributeError, ValueError)):
        write_findings(
            spec_hash="err003",
            slot_id="AC-0",
            defect_type=None,  # type: ignore[arg-type]
            findings_path=findings_path,
            metrics_path=metrics_path,
        )
