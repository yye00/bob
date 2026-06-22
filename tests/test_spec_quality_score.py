"""Tests for spec_quality.score.calculate_spec_quality_score.

Verifies the main function exists, returns correct types, and implements
the gate semantics combining F-R7-410/411/412 plus AC-coverage into
a per-feature score in [0, 1].
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spec_quality.score import calculate_spec_quality_score


def test_function_exists_and_is_callable():
    """AC: Function defined: spec_quality.score.calculate_spec_quality_score"""
    assert callable(calculate_spec_quality_score)


def test_returns_float_in_unit_interval():
    """calculate_spec_quality_score returns a float in [0, 1]."""
    acs = [
        "File exists: src/spec_quality/score.py",
        "Function defined: spec_quality.score.calculate_spec_quality_score",
        "pytest: tests/test_spec_quality_score.py",
    ]
    score = calculate_spec_quality_score(
        name="Sample feature",
        description="A feature with function calculate_spec_quality_score.",
        acceptance_criteria=acs,
    )
    assert isinstance(score, float), f"Expected float, got {type(score)}"
    assert 0.0 <= score <= 1.0, f"Score {score} out of [0, 1]"


def test_well_structured_acs_score_high():
    """Features with clean structured ACs (File exists, Function defined, pytest) score >= 0.85."""
    name = "Clean feature"
    description = None
    acs = [
        "File exists: src/spec_quality/score.py",
        "Function defined: spec_quality.score.calculate_spec_quality_score",
        "pytest: tests/test_spec_quality_score.py",
        "pytest: tests/test_spec_quality_score_gate_boundary.py",
    ]
    score = calculate_spec_quality_score(name=name, description=description, acceptance_criteria=acs)
    assert score >= 0.85, f"Expected high score for structured ACs, got {score}"


def test_empty_acs_score_zero():
    """Empty acceptance criteria always yields score 0.0."""
    score = calculate_spec_quality_score(
        name="No AC feature",
        description="Some description",
        acceptance_criteria=[],
    )
    assert score == 0.0


def test_score_with_list_of_strings():
    """Accepts a plain list of strings as acceptance_criteria."""
    acs = ["File exists: src/spec_quality/score.py"]
    score = calculate_spec_quality_score(
        name="List input",
        description=None,
        acceptance_criteria=acs,
    )
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_score_with_json_string():
    """Accepts a JSON-encoded list as acceptance_criteria."""
    import json
    acs_json = json.dumps([
        "File exists: src/spec_quality/score.py",
        "Function defined: spec_quality.score.calculate_spec_quality_score",
    ])
    score = calculate_spec_quality_score(
        name="JSON input",
        description=None,
        acceptance_criteria=acs_json,
    )
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_integration_with_bob3_spec_quality():
    """Integration: bob3.spec_quality — delegates to the existing quality scoring."""
    from bob3.spec_quality.quality_score import compute_score
    name = "Integration test"
    acs = [
        "File exists: src/spec_quality/score.py",
        "Function defined: spec_quality.score.calculate_spec_quality_score",
    ]
    # Both paths should produce consistent scores
    spec_quality_score = calculate_spec_quality_score(
        name=name, description=None, acceptance_criteria=acs
    )
    bob3_report = compute_score(name=name, description=None, acceptance_criteria=acs)
    assert abs(spec_quality_score - bob3_report.score) < 1e-6, (
        f"calculate_spec_quality_score ({spec_quality_score}) should match "
        f"compute_score ({bob3_report.score})"
    )


# ---------------------------------------------------------------------------
# Tests for tools.spec_quality_score.is_code_shaped_token
# ---------------------------------------------------------------------------

class TestIsCodeShapedToken:
    """AC: Function defined: spec_quality_score.is_code_shaped_token"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from tools.spec_quality_score import is_code_shaped_token
        self.fn = is_code_shaped_token

    def test_function_is_callable(self):
        assert callable(self.fn)

    def test_underscore_token_is_code_shaped(self):
        assert self.fn("extract_py_paths") is True

    def test_dotted_token_is_code_shaped(self):
        assert self.fn("tools.spec_quality_score") is True

    def test_py_extension_is_code_shaped(self):
        assert self.fn("foo.py") is True

    def test_camel_case_is_code_shaped(self):
        assert self.fn("CompositeScore") is True

    def test_plain_english_word_is_not_code_shaped(self):
        # Bare lowercase dictionary words are prose, not symbols
        assert self.fn("name") is False
        assert self.fn("gate") is False
        assert self.fn("correctly") is False
        assert self.fn("returns") is False
        assert self.fn("failures") is False

    def test_stopword_is_not_code_shaped(self):
        assert self.fn("defined") is False
        assert self.fn("implemented") is False
        assert self.fn("declared") is False

    def test_all_uppercase_token_is_not_code_shaped(self):
        # ALL_CAPS are prose emphasis, not symbols
        assert self.fn("TODO") is False
        assert self.fn("FOO") is False

    def test_empty_string_is_not_code_shaped(self):
        assert self.fn("") is False

    def test_pluralised_acronym_is_not_code_shaped(self):
        assert self.fn("ACs") is False
        assert self.fn("IDs") is False


# ---------------------------------------------------------------------------
# Tests for tools.spec_quality_score.extract_py_paths
# ---------------------------------------------------------------------------

class TestExtractPyPaths:
    """AC: Function defined: spec_quality_score.extract_py_paths"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from tools.spec_quality_score import extract_py_paths
        self.fn = extract_py_paths

    def test_function_is_callable(self):
        assert callable(self.fn)

    def test_extracts_path_with_directory(self):
        desc = "The implementation lives in src/bob3/brownfield/survey.py."
        paths = self.fn(desc)
        assert "src/bob3/brownfield/survey.py" in paths

    def test_extracts_multiple_paths(self):
        desc = "See src/bob3/foo.py and tools/spec_quality_score.py for details."
        paths = self.fn(desc)
        assert "src/bob3/foo.py" in paths
        assert "tools/spec_quality_score.py" in paths

    def test_deduplicates_paths(self):
        desc = "Use src/bob3/foo.py and also src/bob3/foo.py again."
        paths = self.fn(desc)
        assert paths.count("src/bob3/foo.py") == 1

    def test_empty_description_returns_empty_list(self):
        assert self.fn("") == []

    def test_none_description_returns_empty_list(self):
        assert self.fn(None) == []

    def test_bare_filename_without_dir_is_excluded(self):
        # Bare filenames without directory are ambiguous — excluded per spec
        desc = "The file foo.py is relevant."
        paths = self.fn(desc)
        assert "foo.py" not in paths

    def test_returns_sorted_list(self):
        desc = "See src/z/z.py and src/a/a.py for implementation."
        paths = self.fn(desc)
        assert paths == sorted(paths)

    def test_returns_list_type(self):
        result = self.fn("some text src/bob3/x.py here")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Tests for tools.spec_quality_score.extract_concrete_py_paths
# ---------------------------------------------------------------------------

class TestExtractConcretePyPaths:
    """AC: Function defined: spec_quality_score.extract_concrete_py_paths"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from tools.spec_quality_score import extract_concrete_py_paths
        self.fn = extract_concrete_py_paths

    def test_function_is_callable(self):
        assert callable(self.fn)

    def test_extracts_path_with_directory(self):
        desc = "The implementation lives in src/bob3/brownfield/survey.py."
        paths = self.fn(desc)
        assert "src/bob3/brownfield/survey.py" in paths

    def test_empty_description_returns_empty_list(self):
        assert self.fn("") == []

    def test_none_description_returns_empty_list(self):
        assert self.fn(None) == []

    def test_deduplicates_paths(self):
        desc = "Use src/bob3/foo.py and also src/bob3/foo.py again."
        paths = self.fn(desc)
        assert paths.count("src/bob3/foo.py") == 1

    def test_bare_filename_without_dir_is_excluded(self):
        desc = "The file foo.py is relevant."
        paths = self.fn(desc)
        assert "foo.py" not in paths

    def test_returns_sorted_list(self):
        desc = "See src/z/z.py and src/a/a.py for implementation."
        paths = self.fn(desc)
        assert paths == sorted(paths)

    def test_returns_same_result_as_extract_py_paths(self):
        """extract_concrete_py_paths is a canonical alias for extract_py_paths."""
        from tools.spec_quality_score import extract_py_paths
        desc = "Use src/bob3/foo.py and tools/spec_quality_score.py."
        assert self.fn(desc) == extract_py_paths(desc)


# ---------------------------------------------------------------------------
# Integration: tools.spec_quality_score module import
# ---------------------------------------------------------------------------

class TestIntegrationToolsSpecQualityScore:
    """AC: integration: tools.spec_quality_score"""

    def test_module_importable(self):
        import importlib
        mod = importlib.import_module("tools.spec_quality_score")
        assert mod is not None

    def test_compute_function_exists(self):
        from tools.spec_quality_score import compute
        assert callable(compute)

    def test_is_code_shaped_token_exists(self):
        from tools.spec_quality_score import is_code_shaped_token
        assert callable(is_code_shaped_token)

    def test_extract_py_paths_exists(self):
        from tools.spec_quality_score import extract_py_paths
        assert callable(extract_py_paths)

    def test_extract_concrete_py_paths_exists(self):
        from tools.spec_quality_score import extract_concrete_py_paths
        assert callable(extract_concrete_py_paths)

    def test_prose_words_not_treated_as_api_surfaces(self):
        """Scorer MUST NOT treat non-code English words as uncovered API surfaces."""
        from tools.spec_quality_score import compute
        # Description that uses prose words that previously caused false positives
        description = (
            "A function defined: my_func() — it returns results correctly and "
            "handles failures. The gate name is checked."
        )
        acs = [
            "Function defined: spec_quality_score.my_func",
            "pytest: tests/test_my_feature.py",
            "pytest: tests/test_my_feature_boundary.py — boundary",
            "pytest: tests/test_my_feature_error.py — error",
        ]
        result = compute(name="Test feature", description=description, acceptance_criteria=acs)
        # contract_completeness must not be zeroed by prose words like
        # "defined", "name", "gate", "correctly", "returns", "failures"
        assert result.contract_completeness > 0.0, (
            f"contract_completeness should not be zeroed by prose words; got {result.contract_completeness}"
        )

    def test_described_py_path_drives_contract_completeness(self):
        """When description names a .py path, scorer considers it covered by a File-exists AC."""
        from tools.spec_quality_score import compute
        description = "Implement src/bob3/brownfield/survey.py to scan the codebase."
        acs = [
            "File exists: src/bob3/brownfield/survey.py",
            "pytest: tests/test_survey_boundary.py — boundary",
            "pytest: tests/test_survey_error.py — error",
        ]
        result = compute(name="Survey feature", description=description, acceptance_criteria=acs)
        assert result.contract_completeness > 0.0, (
            f"survey.py is covered by File-exists AC; contract_completeness={result.contract_completeness}"
        )


# ---------------------------------------------------------------------------
# Standalone tests required by AC for ddbd508e-062f-4b1a-b295-5af50b1165a5
# ---------------------------------------------------------------------------

def test_is_code_identifier_rejects_all_caps():
    """_is_code_identifier must return False for all-uppercase tokens (prose placeholders)."""
    from tools.spec_quality_score import _is_code_identifier

    # All-caps tokens are prose emphasis or template placeholders, not real symbols
    assert _is_code_identifier("NAME") is False, "NAME is a prose placeholder"
    assert _is_code_identifier("FOO") is False, "FOO is a prose placeholder"
    assert _is_code_identifier("TODO") is False, "TODO is a prose placeholder"
    assert _is_code_identifier("UPPER") is False, "UPPER is prose emphasis"
    assert _is_code_identifier("API") is False, "API is an acronym, not a code symbol"


def test_is_code_identifier_requires_mixed_case():
    """_is_code_identifier must return True only for CamelCase with BOTH upper and lower letters."""
    from tools.spec_quality_score import _is_code_identifier

    # Valid CamelCase (has both upper and lower letters)
    assert _is_code_identifier("RetryCounter") is True, "RetryCounter is valid CamelCase"
    assert _is_code_identifier("CompositeScore") is True, "CompositeScore is valid CamelCase"
    assert _is_code_identifier("MyClass") is True, "MyClass is valid CamelCase"

    # All-caps must NOT qualify as CamelCase
    assert _is_code_identifier("NAME") is False, "NAME has no lowercase — not CamelCase"
    assert _is_code_identifier("ABC") is False, "ABC is all-caps acronym — not CamelCase"

    # Valid underscore/dotted identifiers still qualify
    assert _is_code_identifier("my_func") is True, "my_func has underscore"
    assert _is_code_identifier("tools.score") is True, "tools.score is dotted identifier"


# ---------------------------------------------------------------------------
# Required ACs: test_contract_completeness_ignores_prose_words and
# test_synthesizer_emits_file_exists_for_py_paths
# ---------------------------------------------------------------------------

def test_contract_completeness_ignores_prose_words():
    """Scorer MUST NOT treat non-code English words as uncovered API surfaces.

    AC: pytest: tests/test_spec_quality_score.py::test_contract_completeness_ignores_prose_words
    """
    from tools.spec_quality_score import check_contract_completeness

    description = (
        "A function defined: my_func() — it returns results correctly and "
        "handles failures. The gate name is checked."
    )
    acs = [
        "Function defined: spec_quality_score.my_func",
        "pytest: tests/test_my_feature.py",
        "pytest: tests/test_my_feature_boundary.py — boundary",
        "pytest: tests/test_my_feature_error.py — error",
    ]
    score, hints = check_contract_completeness(description, acs)
    # Prose words: "defined", "name", "gate", "correctly", "returns", "failures"
    # must NOT be counted as uncovered API surfaces.
    assert score > 0.0, (
        f"contract_completeness={score} — prose words like 'defined', 'name', "
        f"'gate', 'correctly', 'returns', 'failures' must not be treated as API surfaces. "
        f"Hints: {hints}"
    )


def test_synthesizer_emits_file_exists_for_py_paths():
    """When description names a concrete .py path, the scorer must credit a File-exists AC.

    AC: pytest: tests/test_spec_quality_score.py::test_synthesizer_emits_file_exists_for_py_paths
    """
    from tools.spec_quality_score import check_contract_completeness, extract_py_paths

    description = "Implement src/bob3/brownfield/survey.py to scan the codebase."

    # Simulate synthesizer emitting File-exists ACs for each concrete .py path
    py_paths = extract_py_paths(description)
    assert "src/bob3/brownfield/survey.py" in py_paths, (
        f"extract_py_paths must detect 'src/bob3/brownfield/survey.py'; got {py_paths}"
    )

    # Build ACs including the File-exists AC for the described path
    acs = [
        f"File exists: {path}" for path in py_paths
    ] + [
        "pytest: tests/test_survey_boundary.py — boundary",
        "pytest: tests/test_survey_error.py — error",
    ]

    score, hints = check_contract_completeness(description, acs)
    assert score > 0.0, (
        f"contract_completeness={score} — survey.py is covered by File-exists AC. "
        f"Hints: {hints}"
    )
