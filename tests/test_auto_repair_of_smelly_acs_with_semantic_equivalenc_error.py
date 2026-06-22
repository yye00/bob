"""Error path tests for auto_repair — invalid input raises ValueError and does not silently succeed."""

from __future__ import annotations

import pytest

from auto_repair import semantic_equivalence_check, apply_error_severity_rewrites


class TestSemanticEquivalenceCheckErrorPath:
    def test_non_string_original_raises_value_error(self):
        with pytest.raises(ValueError):
            semantic_equivalence_check(123, "rewrite")  # type: ignore[arg-type]

    def test_non_string_rewrite_raises_value_error(self):
        with pytest.raises(ValueError):
            semantic_equivalence_check("original", None)  # type: ignore[arg-type]

    def test_both_none_raises_value_error(self):
        with pytest.raises(ValueError):
            semantic_equivalence_check(None, None)  # type: ignore[arg-type]


class TestApplyErrorSeverityRewritesErrorPath:
    def test_non_string_feature_id_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            apply_error_severity_rewrites(
                feature_id=123,  # type: ignore[arg-type]
                findings=[],
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_non_list_findings_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            apply_error_severity_rewrites(
                feature_id="feat-err-001",
                findings="not-a-list",  # type: ignore[arg-type]
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_non_list_original_acs_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            apply_error_severity_rewrites(
                feature_id="feat-err-002",
                findings=[],
                original_acs="not-a-list",  # type: ignore[arg-type]
                repairs_log=tmp_path / "repairs.log",
            )

    def test_none_feature_id_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            apply_error_severity_rewrites(
                feature_id=None,  # type: ignore[arg-type]
                findings=[],
                original_acs=[],
                repairs_log=tmp_path / "repairs.log",
            )

    def test_finding_missing_required_key_raises_value_error(self, tmp_path):
        bad_finding = {"smell_id": "S09"}  # missing severity, text, etc.
        with pytest.raises((ValueError, KeyError)):
            apply_error_severity_rewrites(
                feature_id="feat-err-003",
                findings=[bad_finding],
                original_acs=["some ac"],
                repairs_log=tmp_path / "repairs.log",
            )
