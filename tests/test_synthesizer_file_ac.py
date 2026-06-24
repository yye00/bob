"""Tests for bob3.synthesizer file-exists AC emission for .py paths in descriptions.

Verifies:
- emit_file_exists_acs injects File-exists ACs for .py paths named in descriptions
- Duplicate paths are not added twice
- Paths without a directory component are skipped (ambiguous)
- should_emit_function_ac works for symbol/description pairs
"""
from __future__ import annotations

import sys
import pathlib

# Ensure project root is on path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest

from bob3.synthesizer import emit_file_exists_acs, should_emit_function_ac


class TestEmitFileExistsAcs:
    def test_emits_file_exists_for_py_path_with_directory(self):
        desc = "Implements src/bob3/brownfield/survey.py with survey functionality."
        criteria, added = emit_file_exists_acs([], desc)
        assert any("src/bob3/brownfield/survey.py" in ac for ac in criteria)
        assert "src/bob3/brownfield/survey.py" in added

    def test_does_not_duplicate_already_covered_path(self):
        desc = "Implements src/bob3/brownfield/survey.py."
        existing = ["File exists: src/bob3/brownfield/survey.py"]
        criteria, added = emit_file_exists_acs(existing, desc)
        assert added == []
        file_acs = [ac for ac in criteria if "File exists" in ac and "survey.py" in ac]
        assert len(file_acs) == 1

    def test_skips_bare_filename_without_directory(self):
        desc = "Creates foo.py with helper functions."
        criteria, added = emit_file_exists_acs([], desc)
        assert added == []

    def test_emits_multiple_paths(self):
        desc = "Adds src/bob3/scorer.py and tools/spec_quality_score.py."
        criteria, added = emit_file_exists_acs([], desc)
        paths = set(added)
        assert "src/bob3/scorer.py" in paths
        assert "tools/spec_quality_score.py" in paths

    def test_empty_description_returns_unchanged_criteria(self):
        existing = ["File exists: src/foo.py"]
        criteria, added = emit_file_exists_acs(existing, "")
        assert criteria == existing
        assert added == []

    def test_none_description_treated_as_empty(self):
        existing = ["File exists: src/foo.py"]
        criteria, added = emit_file_exists_acs(existing, None)
        assert criteria == existing
        assert added == []

    def test_returns_augmented_criteria_list(self):
        desc = "Modifies src/bob3/spec_synthesizer.py."
        criteria, added = emit_file_exists_acs(["pytest: tests/test_foo.py"], desc)
        assert len(criteria) == 2
        assert "pytest: tests/test_foo.py" in criteria

    def test_test_py_path_without_directory_accepted(self):
        # test_*.py files starting with 'test' are accepted even without '/'
        desc = "See tests/test_scorer.py for verification."
        criteria, added = emit_file_exists_acs([], desc)
        assert any("tests/test_scorer.py" in ac for ac in criteria)


class TestShouldEmitFunctionAc:
    def test_emits_for_symbol_in_description(self):
        result = should_emit_function_ac("my_function", "Implements my_function for processing.")
        assert result is True

    def test_does_not_emit_for_symbol_not_in_description(self):
        result = should_emit_function_ac("nonexistent_symbol", "Does something entirely different.")
        assert result is False

    def test_empty_symbol_returns_false(self):
        result = should_emit_function_ac("", "Some description mentioning something.")
        assert result is False

    def test_empty_description_returns_false(self):
        result = should_emit_function_ac("my_func", "")
        assert result is False
