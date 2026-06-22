"""Tests that per-feature auto_repair:false opt-out is respected."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob3.spec_quality.ac_auto_repair import apply_repairs, repair_feature_acs
from bob3.spec_quality.smell_detectors import SmellFinding


def _make_error_finding(text: str = "The system should process requests.") -> SmellFinding:
    return SmellFinding(
        smell_id="S09",
        smell_name="modal-weakness",
        severity="E",
        text=text,
        detail="Uses 'should' where 'shall' is required.",
    )


class TestOptOutRespected:
    """When auto_repair:false is set for a feature, no repairs are applied."""

    def test_opt_out_false_skips_apply_repairs(self, tmp_path: Path) -> None:
        finding = _make_error_finding()
        rewrite = "The system shall process requests."
        equiv_result = (True, "Same observable constraint.")

        with (
            patch("bob3.spec_quality.ac_auto_repair.suggest_rewrite", return_value=rewrite),
            patch("bob3.spec_quality.ac_auto_repair.verify_semantic_equivalence", return_value=equiv_result),
        ):
            repairs = apply_repairs(
                findings=[finding],
                feature_id="feat-optout",
                repairs_log=tmp_path / "repairs.log",
                auto_repair=False,
            )

        assert len(repairs) == 0

    def test_opt_out_false_does_not_write_log(self, tmp_path: Path) -> None:
        finding = _make_error_finding()
        repairs_log = tmp_path / "repairs.log"
        rewrite = "The system shall process requests."
        equiv_result = (True, "Same constraint.")

        with (
            patch("bob3.spec_quality.ac_auto_repair.suggest_rewrite", return_value=rewrite),
            patch("bob3.spec_quality.ac_auto_repair.verify_semantic_equivalence", return_value=equiv_result),
        ):
            apply_repairs(
                findings=[finding],
                feature_id="feat-optout",
                repairs_log=repairs_log,
                auto_repair=False,
            )

        assert not repairs_log.exists()

    def test_opt_in_true_applies_repairs(self, tmp_path: Path) -> None:
        finding = _make_error_finding()
        rewrite = "The system shall process requests."
        equiv_result = (True, "Same observable constraint.")

        with (
            patch("bob3.spec_quality.ac_auto_repair.suggest_rewrite", return_value=rewrite),
            patch("bob3.spec_quality.ac_auto_repair.verify_semantic_equivalence", return_value=equiv_result),
        ):
            repairs = apply_repairs(
                findings=[finding],
                feature_id="feat-optin",
                repairs_log=tmp_path / "repairs.log",
                auto_repair=True,
            )

        assert len(repairs) == 1

    def test_repair_feature_acs_respects_auto_repair_false(self, tmp_path: Path) -> None:
        """repair_feature_acs reads auto_repair from feature config."""
        acs = ["The system should process requests."]

        with (
            patch("bob3.spec_quality.ac_auto_repair.suggest_rewrite", return_value="The system shall process requests."),
            patch("bob3.spec_quality.ac_auto_repair.verify_semantic_equivalence", return_value=(True, "OK")),
        ):
            result = repair_feature_acs(
                feature_id="feat-optout",
                acceptance_criteria=acs,
                auto_repair=False,
                repairs_log=tmp_path / "repairs.log",
            )

        # When opted out, ACs returned unchanged
        assert result["repaired_acs"] == acs
        assert result["repairs_applied"] == []

    def test_repair_feature_acs_applies_when_opted_in(self, tmp_path: Path) -> None:
        acs = ["The system should log events."]
        rewrite = "The system shall log events."

        with (
            patch("bob3.spec_quality.ac_auto_repair.suggest_rewrite", return_value=rewrite),
            patch("bob3.spec_quality.ac_auto_repair.verify_semantic_equivalence", return_value=(True, "Equivalent.")),
        ):
            result = repair_feature_acs(
                feature_id="feat-optin",
                acceptance_criteria=acs,
                auto_repair=True,
                repairs_log=tmp_path / "repairs.log",
            )

        assert result["repaired_acs"] == [rewrite]
        assert len(result["repairs_applied"]) == 1

    def test_repair_feature_acs_default_is_opt_in(self, tmp_path: Path) -> None:
        """Default auto_repair is True (opt-in behavior)."""
        acs = ["The system should handle requests."]
        rewrite = "The system shall handle requests."

        with (
            patch("bob3.spec_quality.ac_auto_repair.suggest_rewrite", return_value=rewrite),
            patch("bob3.spec_quality.ac_auto_repair.verify_semantic_equivalence", return_value=(True, "Equivalent.")),
        ):
            result = repair_feature_acs(
                feature_id="feat-default",
                acceptance_criteria=acs,
                repairs_log=tmp_path / "repairs.log",
            )

        assert result["repaired_acs"] == [rewrite]
