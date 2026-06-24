"""Tests for spec_quality_score token filtering and file-exists AC emission.

Covers:
- is_code_shaped_token: only code-shaped tokens (_, ., .py, CamelCase) treated
  as API surfaces; plain English prose words are NOT treated as surfaces.
- extract_concrete_py_paths: scans description for concrete .py paths.
- emit_file_exists_acs: adds File-exists ACs for .py paths named in description
  but not already covered by criteria.
- _score_contract_completeness: does not penalise plain-English words.
"""
from __future__ import annotations

import pytest

from tools.spec_quality_score import (
    is_code_shaped_token,
    extract_concrete_py_paths,
    compute,
)
from bob.spec_quality_score import (
    emit_file_exists_acs,
    extract_concrete_py_paths as bob_extract_concrete_py_paths,
    is_code_shaped_token as bob_is_code_shaped_token,
)


# ---------------------------------------------------------------------------
# is_code_shaped_token
# ---------------------------------------------------------------------------

class TestIsCodeShapedToken:
    """is_code_shaped_token must return True only for code-shaped tokens."""

    def test_underscore_token_is_code_shaped(self):
        assert is_code_shaped_token("compute_quality_score") is True

    def test_dot_token_is_code_shaped(self):
        assert is_code_shaped_token("spec_quality_score.compute") is True

    def test_py_extension_is_code_shaped(self):
        assert is_code_shaped_token("survey.py") is True

    def test_camel_case_is_code_shaped(self):
        assert is_code_shaped_token("CompositeScore") is True

    def test_plain_english_defined_is_not_code_shaped(self):
        assert is_code_shaped_token("defined") is False

    def test_plain_english_name_is_not_code_shaped(self):
        assert is_code_shaped_token("name") is False

    def test_plain_english_gate_is_not_code_shaped(self):
        assert is_code_shaped_token("gate") is False

    def test_plain_english_correctly_is_not_code_shaped(self):
        assert is_code_shaped_token("correctly") is False

    def test_plain_english_returns_is_not_code_shaped(self):
        assert is_code_shaped_token("returns") is False

    def test_plain_english_failures_is_not_code_shaped(self):
        assert is_code_shaped_token("failures") is False

    def test_all_uppercase_is_not_code_shaped(self):
        # Prose emphasis (NAME, TODO, FOO) — not a real symbol
        assert is_code_shaped_token("NAME") is False

    def test_pluralised_acronym_is_not_code_shaped(self):
        # ACs, IDs — prose abbreviations
        assert is_code_shaped_token("ACs") is False
        assert is_code_shaped_token("IDs") is False

    def test_empty_string_is_not_code_shaped(self):
        assert is_code_shaped_token("") is False

    def test_stopword_is_not_code_shaped(self):
        assert is_code_shaped_token("implemented") is False
        assert is_code_shaped_token("declared") is False

    def test_bob_alias_matches_tools_version(self):
        for tok in ["compute_quality", "defined", "ACs", "CompositeScore", ""]:
            assert bob_is_code_shaped_token(tok) == is_code_shaped_token(tok)


# ---------------------------------------------------------------------------
# extract_concrete_py_paths
# ---------------------------------------------------------------------------

class TestExtractConcretePyPaths:
    """extract_concrete_py_paths must find .py paths with directory components."""

    def test_finds_path_with_slash(self):
        desc = "implement src/bob/brownfield/survey.py for the survey"
        paths = extract_concrete_py_paths(desc)
        assert "src/bob/brownfield/survey.py" in paths

    def test_skips_bare_filename_without_dir(self):
        desc = "implement survey.py for the survey"
        paths = extract_concrete_py_paths(desc)
        assert "survey.py" not in paths

    def test_finds_test_prefixed_bare_filename(self):
        desc = "add tests in test_foo.py"
        paths = extract_concrete_py_paths(desc)
        assert "test_foo.py" in paths

    def test_deduplicates(self):
        desc = "src/foo.py and src/foo.py"
        paths = extract_concrete_py_paths(desc)
        assert paths.count("src/foo.py") == 1

    def test_returns_sorted(self):
        desc = "src/z.py and src/a.py"
        paths = extract_concrete_py_paths(desc)
        assert paths == sorted(paths)

    def test_empty_description(self):
        assert extract_concrete_py_paths("") == []

    def test_none_description(self):
        assert extract_concrete_py_paths(None) == []

    def test_bob_alias_matches_tools_version(self):
        desc = "implement src/bob/brownfield/survey.py"
        assert bob_extract_concrete_py_paths(desc) == extract_concrete_py_paths(desc)

    def test_finds_multiple_paths(self):
        desc = "modify tools/spec_quality_score.py and src/bob/synthesizer.py"
        paths = extract_concrete_py_paths(desc)
        assert "tools/spec_quality_score.py" in paths
        assert "src/bob/synthesizer.py" in paths


# ---------------------------------------------------------------------------
# emit_file_exists_acs
# ---------------------------------------------------------------------------

class TestEmitFileExistsAcs:
    """emit_file_exists_acs must add File-exists ACs for uncovered .py paths."""

    def test_emits_ac_for_uncovered_path(self):
        desc = "implement src/bob/brownfield/survey.py"
        criteria = ["pytest: tests/test_foo.py"]
        result = emit_file_exists_acs(criteria, desc)
        assert any("File exists: src/bob/brownfield/survey.py" in ac for ac in result)

    def test_does_not_duplicate_already_covered_path(self):
        desc = "implement src/bob/brownfield/survey.py"
        criteria = ["File exists: src/bob/brownfield/survey.py"]
        result = emit_file_exists_acs(criteria, desc)
        count = sum(1 for ac in result if "src/bob/brownfield/survey.py" in ac)
        assert count == 1

    def test_no_change_when_no_py_paths_in_description(self):
        desc = "implement the feature"
        criteria = ["pytest: tests/test_foo.py"]
        result = emit_file_exists_acs(criteria, desc)
        assert result == criteria

    def test_no_change_on_empty_description(self):
        criteria = ["pytest: tests/test_foo.py"]
        result = emit_file_exists_acs(criteria, "")
        assert result == criteria

    def test_adds_multiple_uncovered_paths(self):
        desc = "modify tools/spec_quality_score.py and src/bob/synthesizer.py"
        criteria = []
        result = emit_file_exists_acs(criteria, desc)
        paths_added = [ac for ac in result if ac.startswith("File exists:")]
        added_paths = [ac.split("File exists:")[1].strip() for ac in paths_added]
        assert "tools/spec_quality_score.py" in added_paths
        assert "src/bob/synthesizer.py" in added_paths

    def test_skips_bare_filename_without_dir(self):
        desc = "implement survey.py"
        criteria = []
        result = emit_file_exists_acs(criteria, desc)
        assert not any("survey.py" in ac for ac in result)


# ---------------------------------------------------------------------------
# contract_completeness: plain-English words must NOT be treated as surfaces
# ---------------------------------------------------------------------------

class TestContractCompletenessTokenFiltering:
    """The scorer must not treat plain English words as uncovered API surfaces."""

    def test_prose_words_do_not_drive_completeness_to_zero(self):
        """A description with only prose words should score contract_completeness=1.0."""
        desc = (
            "Function defined: <symbol> syntax is used to define acceptance criteria. "
            "The name, gate, correctly, returns, failures words appear in the description."
        )
        acs = [
            "pytest: tests/test_foo.py",
            "File exists: src/foo.py",
        ]
        result = compute(name="test-feature", description=desc, acceptance_criteria=acs)
        assert result.contract_completeness == 1.0, (
            f"Expected contract_completeness=1.0 for prose-only description, "
            f"got {result.contract_completeness}. Hints: {result.rationale}"
        )

    def test_code_shaped_token_in_description_requires_ac(self):
        """A code-shaped symbol in description (e.g. extract_py_paths) needs an AC."""
        desc = "The function extract_py_paths extracts .py paths from descriptions."
        acs = ["pytest: tests/test_foo.py"]
        result = compute(name="test-feature", description=desc, acceptance_criteria=acs)
        # extract_py_paths is code-shaped (has underscore) — must NOT be 1.0
        assert result.contract_completeness < 1.0

    def test_code_shaped_token_covered_by_ac_gives_full_score(self):
        """When a code-shaped symbol has a matching AC, completeness should be 1.0."""
        desc = "The function extract_py_paths extracts .py paths from descriptions."
        acs = [
            "Function defined: bob.spec_quality_score.extract_py_paths",
            "pytest: tests/test_foo.py",
            "File exists: tests/test_foo.py",
        ]
        result = compute(name="test-feature", description=desc, acceptance_criteria=acs)
        assert result.contract_completeness == 1.0, (
            f"Expected 1.0 when symbol is covered, got {result.contract_completeness}. "
            f"Hints: {result.rationale}"
        )
