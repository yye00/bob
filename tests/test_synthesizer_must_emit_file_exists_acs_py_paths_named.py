"""Tests for bob.synthesizer_must_emit_file_exists_acs_py_paths_named.

Covers the two contract_completeness defect fixes:
  (1) SCORER fix: only code-shaped tokens count as API surfaces.
  (2) SYNTHESIZER fix: File-exists ACs are injected for concrete .py paths.
"""

from __future__ import annotations

import pytest

from bob.synthesizer_must_emit_file_exists_acs_py_paths_named import (
    emit_file_exists_acs_for_py_paths,
    extract_code_shaped_api_surfaces,
    synthesizer_must_emit_file_exists_acs_py_paths_named,
)
from tools.spec_quality_score import (
    extract_concrete_py_paths,
    extract_py_paths,
    filter_api_surfaces,
    is_code_shaped_token,
)


# ---------------------------------------------------------------------------
# is_code_shaped_token — scorer fix
# ---------------------------------------------------------------------------

class TestIsCodeShapedToken:
    def test_underscore_is_code_shaped(self):
        assert is_code_shaped_token("my_function") is True

    def test_dot_is_code_shaped(self):
        assert is_code_shaped_token("bob.spec_synthesizer") is True

    def test_py_extension_is_code_shaped(self):
        assert is_code_shaped_token("survey.py") is True

    def test_camelcase_is_code_shaped(self):
        assert is_code_shaped_token("RetryCounter") is True
        assert is_code_shaped_token("ScoreGateReport") is True

    def test_plain_english_words_are_not_code_shaped(self):
        for word in ("defined", "name", "gate", "correctly", "returns", "failures"):
            assert is_code_shaped_token(word) is False, f"{word!r} should not be code-shaped"

    def test_all_uppercase_is_not_code_shaped(self):
        # All-caps like NAME, TODO, FOO are prose emphasis, not real symbols
        assert is_code_shaped_token("NAME") is False
        assert is_code_shaped_token("TODO") is False

    def test_pluralised_acronym_is_not_code_shaped(self):
        # "ACs", "IDs" are prose acronyms, not symbols
        assert is_code_shaped_token("ACs") is False
        assert is_code_shaped_token("IDs") is False

    def test_empty_string_is_not_code_shaped(self):
        assert is_code_shaped_token("") is False

    def test_stopwords_are_not_code_shaped(self):
        for word in ("defined", "implemented", "declared", "created"):
            assert is_code_shaped_token(word) is False


# ---------------------------------------------------------------------------
# filter_api_surfaces
# ---------------------------------------------------------------------------

class TestFilterApiSurfaces:
    def test_filters_out_plain_english(self):
        tokens = ["defined", "name", "gate", "correctly", "returns", "failures"]
        assert filter_api_surfaces(tokens) == []

    def test_keeps_code_shaped_tokens(self):
        tokens = ["my_func", "bob.module", "survey.py", "RetryCounter", "defined"]
        result = filter_api_surfaces(tokens)
        assert "my_func" in result
        assert "bob.module" in result
        assert "survey.py" in result
        assert "RetryCounter" in result
        assert "defined" not in result

    def test_empty_list_returns_empty(self):
        assert filter_api_surfaces([]) == []


# ---------------------------------------------------------------------------
# extract_py_paths / extract_concrete_py_paths — scorer fix
# ---------------------------------------------------------------------------

class TestExtractPyPaths:
    def test_extracts_path_with_directory(self):
        desc = "See src/bob/brownfield/survey.py for details."
        paths = extract_py_paths(desc)
        assert "src/bob/brownfield/survey.py" in paths

    def test_skips_bare_filename(self):
        desc = "The file survey.py is the module."
        paths = extract_py_paths(desc)
        # bare filename without '/' should be skipped
        assert "survey.py" not in paths

    def test_extracts_test_prefixed_file(self):
        desc = "Run tests/test_foo.py to verify."
        paths = extract_py_paths(desc)
        assert "tests/test_foo.py" in paths

    def test_deduplicates(self):
        desc = "See src/bob/foo.py and also src/bob/foo.py again."
        paths = extract_py_paths(desc)
        assert paths.count("src/bob/foo.py") == 1

    def test_empty_description_returns_empty(self):
        assert extract_py_paths("") == []
        assert extract_py_paths(None) == []

    def test_extract_concrete_py_paths_is_alias(self):
        desc = "File at src/bob/brownfield/survey.py."
        assert extract_concrete_py_paths(desc) == extract_py_paths(desc)


# ---------------------------------------------------------------------------
# emit_file_exists_acs_for_py_paths — synthesizer fix
# ---------------------------------------------------------------------------

class TestEmitFileExistsAcsForPyPaths:
    def test_adds_file_exists_ac_for_uncovered_path(self):
        desc = "This feature creates src/bob/brownfield/survey.py."
        criteria = ["Function defined: bob.brownfield.survey.run"]
        augmented, added = emit_file_exists_acs_for_py_paths(criteria, desc)
        assert "File exists: src/bob/brownfield/survey.py" in augmented
        assert "src/bob/brownfield/survey.py" in added

    def test_does_not_duplicate_already_covered_path(self):
        desc = "This feature creates src/bob/brownfield/survey.py."
        criteria = ["File exists: src/bob/brownfield/survey.py"]
        augmented, added = emit_file_exists_acs_for_py_paths(criteria, desc)
        file_exists_count = sum(
            1 for ac in augmented if "src/bob/brownfield/survey.py" in ac
        )
        assert file_exists_count == 1
        assert added == []

    def test_no_py_paths_in_description_returns_unchanged(self):
        desc = "A feature with no concrete file paths."
        criteria = ["Function defined: bob.foo.bar"]
        augmented, added = emit_file_exists_acs_for_py_paths(criteria, desc)
        assert augmented == criteria
        assert added == []

    def test_empty_description_returns_original(self):
        criteria = ["File exists: src/foo.py"]
        augmented, added = emit_file_exists_acs_for_py_paths(criteria, "")
        assert augmented == criteria
        assert added == []

    def test_multiple_paths_all_added(self):
        desc = "Creates src/bob/foo.py and src/bob/bar.py."
        criteria = []
        augmented, added = emit_file_exists_acs_for_py_paths(criteria, desc)
        assert "File exists: src/bob/foo.py" in augmented
        assert "File exists: src/bob/bar.py" in augmented
        assert len(added) == 2


# ---------------------------------------------------------------------------
# extract_code_shaped_api_surfaces
# ---------------------------------------------------------------------------

class TestExtractCodeShapedApiSurfaces:
    def test_extracts_function_name_with_underscore(self):
        desc = "The function some_function does the work."
        surfaces = extract_code_shaped_api_surfaces(desc)
        assert "some_function" in surfaces

    def test_ignores_prose_english_words(self):
        desc = "Function defined: does the work correctly."
        surfaces = extract_code_shaped_api_surfaces(desc)
        assert "correctly" not in surfaces

    def test_extracts_py_paths(self):
        desc = "See src/bob/brownfield/survey.py."
        surfaces = extract_code_shaped_api_surfaces(desc)
        assert "src/bob/brownfield/survey.py" in surfaces

    def test_empty_description_returns_empty(self):
        assert extract_code_shaped_api_surfaces("") == []


# ---------------------------------------------------------------------------
# synthesizer_must_emit_file_exists_acs_py_paths_named — main entry-point
# ---------------------------------------------------------------------------

def test_synthesizer_must_emit_file_exists_acs_py_paths_named():
    """Main AC test: both fixes applied through the primary entry-point."""
    description = (
        "Two contract_completeness defects: "
        "(1) SCORER over-extraction pulled plain English words like 'defined', "
        "'name', 'gate', 'correctly' as API surfaces. "
        "(2) SYNTHESIZER under-coverage: when description names "
        "src/bob/brownfield/survey.py explicitly but synthesis derived a "
        "different slug, the path was uncovered. "
        "Fix: emit File-exists AC for src/bob/brownfield/survey.py and "
        "only treat code-shaped tokens as API surfaces."
    )
    existing_criteria = [
        "Function defined: bob.brownfield.survey.some_function",
        "pytest: tests/test_survey.py",
    ]

    result = synthesizer_must_emit_file_exists_acs_py_paths_named(
        description=description,
        acceptance_criteria=existing_criteria,
    )

    # (1) Synthesizer fix: File-exists AC injected for the named .py path
    assert "File exists: src/bob/brownfield/survey.py" in result["criteria"], (
        "Expected File-exists AC for src/bob/brownfield/survey.py"
    )
    assert "src/bob/brownfield/survey.py" in result["added_paths"]

    # (2) Scorer fix: plain English words not in api_surfaces
    for prose_word in ("defined", "name", "gate", "correctly"):
        assert prose_word not in result["api_surfaces"], (
            f"Prose word {prose_word!r} must not be treated as a code API surface"
        )

    # (3) No duplication — existing ACs preserved
    for ac in existing_criteria:
        assert ac in result["criteria"]

    # (4) Result dict has required keys
    assert "criteria" in result
    assert "added_paths" in result
    assert "api_surfaces" in result


def test_synthesizer_invalid_description_raises():
    """Non-string description raises ValueError."""
    with pytest.raises(ValueError):
        synthesizer_must_emit_file_exists_acs_py_paths_named(description=123)


def test_synthesizer_none_criteria_defaults_to_empty():
    """None criteria defaults to empty list without error."""
    result = synthesizer_must_emit_file_exists_acs_py_paths_named(
        description="Feature at src/bob/foo.py.",
        acceptance_criteria=None,
    )
    assert isinstance(result["criteria"], list)
    assert "File exists: src/bob/foo.py" in result["criteria"]


def test_synthesizer_description_without_py_paths():
    """Description with no .py paths: criteria unchanged, no adds."""
    desc = "A feature that does not name any concrete file paths."
    criteria = ["Function defined: bob.foo.bar"]
    result = synthesizer_must_emit_file_exists_acs_py_paths_named(
        description=desc,
        acceptance_criteria=criteria,
    )
    assert result["added_paths"] == []
    assert result["criteria"] == criteria


def test_synthesizer_no_duplicate_file_exists_acs():
    """If a File-exists AC already covers the path, it is not duplicated."""
    desc = "Creates src/bob/brownfield/survey.py."
    criteria = ["File exists: src/bob/brownfield/survey.py"]
    result = synthesizer_must_emit_file_exists_acs_py_paths_named(
        description=desc,
        acceptance_criteria=criteria,
    )
    count = sum(1 for ac in result["criteria"] if "survey.py" in ac)
    assert count == 1
    assert result["added_paths"] == []
