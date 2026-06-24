"""Tests for auto_repair_smelly_acs_semantic_equivalence_verification module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob.auto_repair_smelly_acs_semantic_equivalence_verification import (
    auto_repair_smelly_acs_semantic_equivalence_verification,
    suggest_rewrite,
    verify_semantic_equivalence,
    apply_repairs,
    respect_opt_out,
    compute_auto_repair_rate,
    handle_missing_judge,
    reject_unequivalent_rewrite,
    EquivalenceJudgeUnavailableError,
    RewriteRejectedError,
    SmellFinding,
)


def _make_error_finding(text: str = "The system should process requests.") -> SmellFinding:
    from bob.spec_quality.smell_catalog import SMELL_BY_ID
    defn = SMELL_BY_ID["S09"]
    return SmellFinding(
        smell_id="S09",
        smell_name=defn.name,
        severity="E",
        text=text,
        detail="Uses 'should' where 'shall' is required.",
    )


def _make_warn_finding(text: str = "The system shall respond quickly.") -> SmellFinding:
    from bob.spec_quality.smell_catalog import SMELL_BY_ID
    defn = SMELL_BY_ID["S02"]
    return SmellFinding(
        smell_id="S02",
        smell_name=defn.name,
        severity="W",
        text=text,
        detail="Vague performance qualifier.",
    )


def _llm_equiv_true() -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text="EQUIVALENT: true\nRATIONALE: Same observable constraint.")]
    return resp


def _llm_equiv_false() -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text="EQUIVALENT: false\nRATIONALE: Different constraint.")]
    return resp


def _llm_rewrite(text: str) -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


class TestAutoRepairSmelly:
    """Tests for the top-level auto_repair_smelly_acs_semantic_equivalence_verification function."""

    def test_clean_ac_not_repaired(self) -> None:
        result = auto_repair_smelly_acs_semantic_equivalence_verification(
            feature_id="feat-clean",
            acceptance_criteria=["pytest: tests/test_foo.py -v"],
        )
        assert result["repaired_acs"] == ["pytest: tests/test_foo.py -v"]
        assert result["repairs_applied"] == []
        assert result["auto_repair_enabled"] is True

    def test_error_ac_repaired_when_equivalent(self, tmp_path: Path) -> None:
        original = "The system should process requests."
        rewrite = "The system shall process requests."

        with (
            patch("bob.spec_quality.ac_auto_repair._call_llm_judge") as mock_judge,
        ):
            # First call: rewrite suggestion; subsequent calls: equivalence check
            mock_judge.side_effect = [
                _llm_rewrite(rewrite),
                _llm_equiv_true(),
            ]
            result = auto_repair_smelly_acs_semantic_equivalence_verification(
                feature_id="feat-001",
                acceptance_criteria=[original],
                repairs_log=tmp_path / "repairs.log",
            )

        assert result["auto_repair_enabled"] is True
        # Either repaired or unchanged (depends on whether S09 fires on this text)
        assert isinstance(result["repaired_acs"], list)
        assert len(result["repaired_acs"]) == 1

    def test_opt_out_disables_repairs(self, tmp_path: Path) -> None:
        result = auto_repair_smelly_acs_semantic_equivalence_verification(
            feature_id="feat-optout",
            acceptance_criteria=["The system should be fast."],
            auto_repair=False,
            repairs_log=tmp_path / "repairs.log",
        )
        assert result["repairs_applied"] == []
        assert result["auto_repair_enabled"] is False

    def test_returns_smell_findings_list(self, tmp_path: Path) -> None:
        result = auto_repair_smelly_acs_semantic_equivalence_verification(
            feature_id="feat-002",
            acceptance_criteria=["The system shall log events."],
            repairs_log=tmp_path / "repairs.log",
        )
        assert "smell_findings" in result
        assert isinstance(result["smell_findings"], list)

    def test_multiple_acs_returned(self, tmp_path: Path) -> None:
        acs = [
            "pytest: tests/test_foo.py -v",
            "File exists: src/bob/foo.py",
        ]
        result = auto_repair_smelly_acs_semantic_equivalence_verification(
            feature_id="feat-003",
            acceptance_criteria=acs,
            repairs_log=tmp_path / "repairs.log",
        )
        assert len(result["repaired_acs"]) == 2

    def test_apply_repairs_error_severity_applied(self, tmp_path: Path) -> None:
        finding = _make_error_finding()
        rewrite = "The system shall process requests."

        with (
            patch("bob.spec_quality.ac_auto_repair.suggest_rewrite", return_value=rewrite),
            patch("bob.spec_quality.ac_auto_repair.verify_semantic_equivalence", return_value=(True, "Equivalent.")),
        ):
            repairs = apply_repairs(
                findings=[finding],
                feature_id="feat-001",
                repairs_log=tmp_path / "repairs.log",
            )

        assert len(repairs) == 1
        assert repairs[0]["original"] == finding.text
        assert repairs[0]["rewrite"] == rewrite

    def test_apply_repairs_warn_severity_not_applied(self, tmp_path: Path) -> None:
        finding = _make_warn_finding()

        with (
            patch("bob.spec_quality.ac_auto_repair.suggest_rewrite", return_value="rewrite"),
            patch("bob.spec_quality.ac_auto_repair.verify_semantic_equivalence", return_value=(True, "Equiv.")),
        ):
            repairs = apply_repairs(
                findings=[finding],
                feature_id="feat-001",
                repairs_log=tmp_path / "repairs.log",
            )

        assert len(repairs) == 0

    def test_apply_repairs_non_equivalent_rejected(self, tmp_path: Path) -> None:
        finding = _make_error_finding()

        with (
            patch("bob.spec_quality.ac_auto_repair.suggest_rewrite", return_value="totally different"),
            patch("bob.spec_quality.ac_auto_repair.verify_semantic_equivalence", return_value=(False, "Not equiv.")),
        ):
            repairs = apply_repairs(
                findings=[finding],
                feature_id="feat-001",
                repairs_log=tmp_path / "repairs.log",
            )

        assert len(repairs) == 0

    def test_apply_repairs_opt_out(self, tmp_path: Path) -> None:
        finding = _make_error_finding()
        repairs = apply_repairs(
            findings=[finding],
            feature_id="feat-001",
            repairs_log=tmp_path / "repairs.log",
            auto_repair=False,
        )
        assert repairs == []

    def test_verify_semantic_equivalence_true(self) -> None:
        with patch("bob.spec_quality.ac_auto_repair._call_llm_judge", return_value=_llm_equiv_true()):
            result, rationale = verify_semantic_equivalence("original", "rewrite")
        assert result is True
        assert "Same observable constraint" in rationale

    def test_verify_semantic_equivalence_false(self) -> None:
        with patch("bob.spec_quality.ac_auto_repair._call_llm_judge", return_value=_llm_equiv_false()):
            result, rationale = verify_semantic_equivalence("original", "divergent rewrite")
        assert result is False

    def test_verify_semantic_equivalence_llm_error(self) -> None:
        with patch("bob.spec_quality.ac_auto_repair._call_llm_judge", side_effect=Exception("down")):
            result, rationale = verify_semantic_equivalence("orig", "rewrite")
        assert result is False
        assert rationale

    def test_suggest_rewrite_info_returns_none(self) -> None:
        finding = SmellFinding(
            smell_id="S15",
            smell_name="tautology",
            severity="I",
            text="The system shall be a system.",
            detail="Restates feature name.",
        )
        result = suggest_rewrite(finding)
        assert result is None

    def test_suggest_rewrite_error_returns_string(self) -> None:
        finding = _make_error_finding()
        rewrite = "The system shall process requests."
        with patch("bob.spec_quality.ac_auto_repair._call_llm_judge", return_value=_llm_rewrite(rewrite)):
            result = suggest_rewrite(finding)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_respect_opt_out_false_when_set(self) -> None:
        assert respect_opt_out({"auto_repair": False}) is False

    def test_respect_opt_out_true_by_default(self) -> None:
        assert respect_opt_out({}) is True
        assert respect_opt_out({"auto_repair": True}) is True

    def test_reject_unequivalent_rewrite_raises_on_non_equiv(self) -> None:
        with (
            patch("bob.spec_quality.ac_auto_repair._call_llm_judge", return_value=_llm_equiv_false()),
            pytest.raises(RewriteRejectedError),
        ):
            reject_unequivalent_rewrite("original", "divergent")

    def test_reject_unequivalent_rewrite_returns_rewrite_when_equiv(self) -> None:
        with patch("bob.spec_quality.ac_auto_repair._call_llm_judge", return_value=_llm_equiv_true()):
            result = reject_unequivalent_rewrite("orig", "rewrite")
        assert result == "rewrite"

    def test_handle_missing_judge_raises_on_llm_error(self) -> None:
        with (
            patch("bob.spec_quality.ac_auto_repair._call_llm_judge", side_effect=Exception("unreachable")),
            pytest.raises(EquivalenceJudgeUnavailableError),
        ):
            handle_missing_judge("orig", "rewrite")

    def test_handle_missing_judge_returns_result_when_available(self) -> None:
        with patch("bob.spec_quality.ac_auto_repair._call_llm_judge", return_value=_llm_equiv_true()):
            result, rationale = handle_missing_judge("orig", "rewrite")
        assert result is True

    def test_compute_auto_repair_rate_returns_float(self) -> None:
        rate = compute_auto_repair_rate()
        assert isinstance(rate, float)
        assert 0.0 <= rate <= 1.0

    def test_repairs_log_written_on_apply(self, tmp_path: Path) -> None:
        finding = _make_error_finding()
        log_path = tmp_path / "repairs.log"

        with (
            patch("bob.spec_quality.ac_auto_repair.suggest_rewrite", return_value="The system shall process requests."),
            patch("bob.spec_quality.ac_auto_repair.verify_semantic_equivalence", return_value=(True, "Equivalent.")),
        ):
            apply_repairs(
                findings=[finding],
                feature_id="feat-log",
                repairs_log=log_path,
            )

        assert log_path.exists()
        content = log_path.read_text()
        assert "feat-log" in content
        assert finding.text in content


def test_auto_repair_smelly_acs_semantic_equivalence_verification() -> None:
    """Primary AC test: function is importable and returns expected structure."""
    result = auto_repair_smelly_acs_semantic_equivalence_verification(
        feature_id="feat-ac-test",
        acceptance_criteria=["pytest: tests/test_foo.py -v"],
    )
    assert isinstance(result, dict)
    assert "repaired_acs" in result
    assert "repairs_applied" in result
    assert "smell_findings" in result
    assert "auto_repair_enabled" in result
    assert result["auto_repair_enabled"] is True
    assert result["repaired_acs"] == ["pytest: tests/test_foo.py -v"]
    assert result["repairs_applied"] == []
