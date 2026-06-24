"""Tests for spec_quality_score scorer token filtering (filter_code_shaped_surfaces).

Verifies that:
- filter_code_shaped_surfaces only returns code-shaped tokens (_, ., .py, CamelCase)
- Plain English prose words are filtered out and NOT treated as API surfaces
- The scorer (contract_completeness) does not penalise prose-only descriptions
"""
from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest

from tools.spec_quality_score import (
    is_code_shaped_token,
    filter_code_shaped_surfaces,
    compute,
)


class TestFilterCodeShapedSurfaces:
    """filter_code_shaped_surfaces must exclude plain English words."""

    def test_keeps_underscore_symbol(self):
        result = filter_code_shaped_surfaces(["compute_quality_score", "defined"])
        assert "compute_quality_score" in result
        assert "defined" not in result

    def test_keeps_dotted_path(self):
        result = filter_code_shaped_surfaces(["spec_quality.compute", "name"])
        assert "spec_quality.compute" in result
        assert "name" not in result

    def test_keeps_py_extension(self):
        result = filter_code_shaped_surfaces(["tools/survey.py", "gate"])
        assert "tools/survey.py" in result
        assert "gate" not in result

    def test_keeps_camel_case(self):
        result = filter_code_shaped_surfaces(["CompositeScore", "correctly"])
        assert "CompositeScore" in result
        assert "correctly" not in result

    def test_filters_all_english_stopwords(self):
        prose_words = ["defined", "name", "gate", "correctly", "returns", "failures",
                       "implemented", "declared"]
        result = filter_code_shaped_surfaces(prose_words)
        assert result == [], f"Expected empty, got {result}"

    def test_empty_list_returns_empty(self):
        assert filter_code_shaped_surfaces([]) == []

    def test_mixed_list_keeps_only_code_shaped(self):
        tokens = ["extract_py_paths", "defined", "CompositeScore", "name"]
        result = filter_code_shaped_surfaces(tokens)
        assert "extract_py_paths" in result
        assert "CompositeScore" in result
        assert "defined" not in result
        assert "name" not in result


class TestScorerDoesNotPenaliseProse:
    """Scorer must not treat prose English words as uncovered API surfaces."""

    def test_prose_description_does_not_drive_completeness_to_zero(self):
        desc = (
            "Function defined: <symbol> syntax describes the AC form. "
            "The name, gate, correctly, returns, failures words appear here."
        )
        acs = ["pytest: tests/test_foo.py", "File exists: src/foo.py"]
        result = compute(name="test-feature", description=desc, acceptance_criteria=acs)
        assert result.contract_completeness == 1.0, (
            f"Expected 1.0 for prose-only description, got {result.contract_completeness}. "
            f"Rationale: {result.rationale}"
        )

    def test_code_shaped_symbol_without_ac_reduces_score(self):
        desc = "The function extract_py_paths extracts .py paths from descriptions."
        acs = ["pytest: tests/test_foo.py"]
        result = compute(name="test-feature", description=desc, acceptance_criteria=acs)
        # extract_py_paths is code-shaped; no AC covers it → score < 1.0
        assert result.contract_completeness < 1.0

    def test_code_shaped_symbol_covered_by_ac_gives_full_score(self):
        desc = "The function extract_py_paths extracts .py paths from descriptions."
        acs = [
            "Function defined: bob.spec_quality_score.extract_py_paths",
            "pytest: tests/test_foo.py",
            "File exists: tests/test_foo.py",
        ]
        result = compute(name="test-feature", description=desc, acceptance_criteria=acs)
        assert result.contract_completeness == 1.0, (
            f"Expected 1.0 when symbol is covered, got {result.contract_completeness}. "
            f"Rationale: {result.rationale}"
        )
