"""Feature 0ffd06f6 — Synthesizer MUST emit File-exists ACs for .py paths named
in the description, and the scorer MUST only treat code-shaped tokens as API
surfaces.

Two contract_completeness defects zeroed the composite spec-quality score:

  (1) SCORER over-extraction: plain English words ("defined", "name", "gate",
      "correctly", "returns", "failures") were pulled as "API surfaces" and each
      demanded an AC → contract_completeness=0. A surface token only counts when
      it is CODE-SHAPED and not an English stop-word.

  (2) SYNTHESIZER under-coverage: a description that explicitly names a concrete
      source path (e.g. src/bob/brownfield/survey.py) but whose synthesis derived
      a different slug filename left the described path uncovered →
      contract_completeness=0. Post-synthesis, the described path must get a
      `File exists:` AC.
"""
import importlib

import pytest

from bob.spec_synthesis import emit_file_exists_acs_for_described_paths
from tools.spec_quality_score import _contract_completeness, is_code_shaped_token


# ---------------------------------------------------------------------------
# Defect (2): SYNTHESIZER — emit File-exists ACs for described .py paths
# ---------------------------------------------------------------------------

def test_named_path_gets_file_exists_ac():
    desc = "Fix the brownfield survey in src/bob/brownfield/survey.py so it works."
    result = emit_file_exists_acs_for_described_paths([], desc)
    assert "File exists: src/bob/brownfield/survey.py" in result


def test_already_covered_path_not_double_added():
    desc = "See src/bob/brownfield/survey.py."
    criteria = ["File exists: src/bob/brownfield/survey.py"]
    result = emit_file_exists_acs_for_described_paths(criteria, desc)
    count = sum(
        1 for c in result if c == "File exists: src/bob/brownfield/survey.py"
    )
    assert count == 1


def test_no_paths_leaves_criteria_unchanged():
    criteria = ["Function defined: mod.fn", "pytest: tests/test_x.py"]
    result = emit_file_exists_acs_for_described_paths(criteria, "no paths here")
    assert result == criteria


def test_bare_filename_without_directory_is_skipped():
    result = emit_file_exists_acs_for_described_paths([], "just foo.py by itself")
    assert not any(c.startswith("File exists:") for c in result)


def test_multiple_paths_each_emitted_once():
    desc = "Touch src/bob/a_module.py and tools/b_module.py to fix it."
    result = emit_file_exists_acs_for_described_paths([], desc)
    assert "File exists: src/bob/a_module.py" in result
    assert "File exists: tools/b_module.py" in result


def test_returns_fresh_list_not_mutating_input():
    criteria = ["pytest: tests/test_x.py"]
    result = emit_file_exists_acs_for_described_paths(criteria, "src/bob/z.py named")
    assert criteria == ["pytest: tests/test_x.py"]
    assert result is not criteria


# ---------------------------------------------------------------------------
# Defect (1): SCORER — only code-shaped tokens count as API surfaces
# ---------------------------------------------------------------------------

def test_prose_words_are_not_treated_as_api_surfaces():
    # These prose words previously drove contract_completeness to 0.
    for word in ("defined", "name", "gate", "correctly", "returns", "failures"):
        assert is_code_shaped_token(word) is False, word


def test_code_shaped_tokens_are_recognized():
    for token in ("foo_bar", "mod.fn", "survey.py", "RetryCounter"):
        assert is_code_shaped_token(token) is True, token


def test_scorer_ignores_prose_only_description():
    desc = "The gate returns failures correctly when defined by name."
    score, hints = _contract_completeness(desc, ["pytest: tests/test_x.py"])
    assert score == 1.0
    assert hints == []


def test_scorer_covered_when_file_exists_ac_present():
    desc = "Create module src/bob/foo_bar.py to do the work."
    score, hints = _contract_completeness(
        desc, ["File exists: src/bob/foo_bar.py"]
    )
    assert score == 1.0
    assert hints == []


def test_synthesizer_output_makes_scorer_complete():
    # End-to-end: an uncovered described path is flagged by the scorer, then
    # the synthesizer's emitted File-exists AC makes the contract complete.
    desc = "Implement module src/bob/foo_bar.py per spec."
    base = ["pytest: tests/test_x.py"]
    score_before, hints_before = _contract_completeness(desc, base)
    assert score_before < 1.0
    assert hints_before

    augmented = emit_file_exists_acs_for_described_paths(base, desc)
    score_after, hints_after = _contract_completeness(desc, augmented)
    assert score_after == 1.0
    assert hints_after == []


# ---------------------------------------------------------------------------
# Integration: tools.spec_quality_score is importable and wired
# ---------------------------------------------------------------------------

def test_integration_spec_quality_score_importable():
    mod = importlib.import_module("tools.spec_quality_score")
    assert hasattr(mod, "_contract_completeness")
    assert callable(mod._contract_completeness)


# ---------------------------------------------------------------------------
# Error path: invalid input raises ValueError (does not silently succeed)
# ---------------------------------------------------------------------------

def test_non_list_criteria_raises():
    with pytest.raises(ValueError):
        emit_file_exists_acs_for_described_paths("not a list", "src/bob/z.py")


def test_non_string_criteria_item_raises():
    with pytest.raises(ValueError):
        emit_file_exists_acs_for_described_paths([123], "src/bob/z.py")


def test_non_string_description_raises():
    with pytest.raises(ValueError):
        emit_file_exists_acs_for_described_paths([], 123)
