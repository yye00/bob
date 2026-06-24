"""Tests that ERROR-severity rewrites are auto-applied when equivalence passes."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob3.spec_quality.ac_auto_repair import apply_repairs
from bob3.spec_quality.smell_detectors import SmellFinding


def _make_finding(smell_id: str, severity: str, text: str) -> SmellFinding:
    from bob3.spec_quality.smell_catalog import SMELL_BY_ID
    defn = SMELL_BY_ID[smell_id]
    return SmellFinding(
        smell_id=smell_id,
        smell_name=defn.name,
        severity=defn.severity,  # type: ignore[arg-type]
        text=text,
        detail=f"Detected {defn.name}",
    )


class TestApplyRepairs:
    """apply_repairs must auto-apply ERROR-severity rewrites that pass equivalence."""

    def test_error_severity_applied_when_equivalent(self, tmp_path: Path) -> None:
        finding = _make_finding("S09", "E", "The system should process requests.")

        equiv_result = (True, "Same observable constraint.")
        rewrite = "The system shall process requests."

        with (
            patch("bob3.spec_quality.ac_auto_repair.suggest_rewrite", return_value=rewrite),
            patch("bob3.spec_quality.ac_auto_repair.verify_semantic_equivalence", return_value=equiv_result),
        ):
            repairs = apply_repairs(
                findings=[finding],
                feature_id="feat-001",
                repairs_log=tmp_path / "repairs.log",
            )

        assert len(repairs) == 1
        assert repairs[0]["original"] == finding.text
        assert repairs[0]["rewrite"] == rewrite
        assert "rationale" in repairs[0]

    def test_error_severity_not_applied_when_not_equivalent(self, tmp_path: Path) -> None:
        finding = _make_finding("S09", "E", "The system should process requests quickly.")

        equiv_result = (False, "Different observable constraint.")
        rewrite = "The system shall respond within 200ms."

        with (
            patch("bob3.spec_quality.ac_auto_repair.suggest_rewrite", return_value=rewrite),
            patch("bob3.spec_quality.ac_auto_repair.verify_semantic_equivalence", return_value=equiv_result),
        ):
            repairs = apply_repairs(
                findings=[finding],
                feature_id="feat-001",
                repairs_log=tmp_path / "repairs.log",
            )

        assert len(repairs) == 0

    def test_warn_severity_not_auto_applied(self, tmp_path: Path) -> None:
        finding = _make_finding("S02", "W", "The system shall respond quickly.")

        equiv_result = (True, "Same constraint.")
        rewrite = "The system shall respond within 100ms."

        with (
            patch("bob3.spec_quality.ac_auto_repair.suggest_rewrite", return_value=rewrite),
            patch("bob3.spec_quality.ac_auto_repair.verify_semantic_equivalence", return_value=equiv_result),
        ):
            repairs = apply_repairs(
                findings=[finding],
                feature_id="feat-001",
                repairs_log=tmp_path / "repairs.log",
            )

        # WARN severity should NOT be auto-applied
        assert len(repairs) == 0

    def test_repairs_logged_to_file(self, tmp_path: Path) -> None:
        finding = _make_finding("S09", "E", "The system should process requests.")
        repairs_log = tmp_path / "repairs.log"

        equiv_result = (True, "Same observable constraint.")
        rewrite = "The system shall process requests."

        with (
            patch("bob3.spec_quality.ac_auto_repair.suggest_rewrite", return_value=rewrite),
            patch("bob3.spec_quality.ac_auto_repair.verify_semantic_equivalence", return_value=equiv_result),
        ):
            apply_repairs(
                findings=[finding],
                feature_id="feat-001",
                repairs_log=repairs_log,
            )

        assert repairs_log.exists()
        content = repairs_log.read_text()
        assert "feat-001" in content
        assert finding.text in content
        assert rewrite in content

    def test_no_rewrite_skips_finding(self, tmp_path: Path) -> None:
        finding = _make_finding("S09", "E", "The system should process requests.")

        with (
            patch("bob3.spec_quality.ac_auto_repair.suggest_rewrite", return_value=None),
        ):
            repairs = apply_repairs(
                findings=[finding],
                feature_id="feat-001",
                repairs_log=tmp_path / "repairs.log",
            )

        assert len(repairs) == 0

    def test_multiple_findings_mixed_outcomes(self, tmp_path: Path) -> None:
        error_finding = _make_finding("S09", "E", "The system should log events.")
        warn_finding = _make_finding("S02", "W", "The system shall respond quickly.")

        def mock_suggest(finding: SmellFinding) -> str | None:
            return "The system shall log events." if finding.severity == "E" else None

        equiv_result = (True, "Equivalent.")

        with (
            patch("bob3.spec_quality.ac_auto_repair.suggest_rewrite", side_effect=mock_suggest),
            patch("bob3.spec_quality.ac_auto_repair.verify_semantic_equivalence", return_value=equiv_result),
        ):
            repairs = apply_repairs(
                findings=[error_finding, warn_finding],
                feature_id="feat-002",
                repairs_log=tmp_path / "repairs.log",
            )

        assert len(repairs) == 1
        assert repairs[0]["original"] == error_finding.text
