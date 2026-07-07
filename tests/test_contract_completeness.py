"""Tests for the two contract_completeness defects.

(1) SCORER over-extraction: `_contract_completeness` must only treat
    code-shaped tokens as API surfaces — plain English words (defined, name,
    gate, correctly, returns, failures) are prose, not symbols.
(2) SYNTHESIZER under-coverage: when a description names a concrete .py path,
    a `File exists:` AC must be emitted for it (unless already covered).
"""
import importlib

import pytest

mod = importlib.import_module("tools.spec_quality_score")


# --------------------------------------------------------------------------
# Symbol presence (AC: Function defined: tools.spec_quality_score._contract_completeness)
# --------------------------------------------------------------------------

def test_contract_completeness_symbol_defined():
    assert hasattr(mod, "_contract_completeness")
    assert callable(mod._contract_completeness)


# --------------------------------------------------------------------------
# (1) Scorer must NOT treat plain English words as API surfaces
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "word",
    ["defined", "name", "gate", "correctly", "returns", "failures"],
)
def test_prose_words_are_not_code_shaped(word):
    assert mod.is_code_shaped_token(word) is False


def test_code_shaped_tokens_recognised():
    assert mod.is_code_shaped_token("run_loop") is True
    assert mod.is_code_shaped_token("survey.py") is True
    assert mod.is_code_shaped_token("RetryCounter") is True
    assert mod.is_code_shaped_token("mod.func") is True


def test_scorer_ignores_prose_and_scores_full():
    # A description that describes the `Function defined: <symbol>` AC syntax
    # uses the bare word "defined" in prose — this must NOT be demanded as an AC.
    description = (
        "The gate must be defined correctly so that the name returns without "
        "failures when a symbol is declared."
    )
    score, hints = mod._contract_completeness(description, [])
    assert score == 1.0
    assert hints == []


def test_scorer_demands_ac_for_real_symbol():
    description = "Function run_loop must be defined."
    score, hints = mod._contract_completeness(description, [])
    assert score < 1.0
    assert any("run_loop" in h for h in hints)


def test_scorer_credits_covered_symbol():
    description = "Function run_loop must be defined."
    acs = ["Function defined: bob.run_loop.run_loop"]
    score, hints = mod._contract_completeness(description, acs)
    assert score == 1.0
    assert hints == []


def test_scorer_none_description_is_neutral():
    score, hints = mod._contract_completeness(None, [])
    assert score == 1.0
    assert hints == []


# --------------------------------------------------------------------------
# (2) Synthesizer must emit File-exists ACs for concrete .py paths
# --------------------------------------------------------------------------

def test_extract_py_paths_finds_concrete_path():
    description = "Implement it in src/bob/brownfield/survey.py please."
    paths = mod.extract_py_paths(description)
    assert "src/bob/brownfield/survey.py" in paths


def test_extract_py_paths_skips_bare_filenames():
    # Bare filename without a directory component is ambiguous → skipped.
    description = "See foo.py for details."
    assert "foo.py" not in mod.extract_py_paths(description)


def test_extract_py_paths_dedupes():
    description = "a/b.py and again a/b.py"
    assert mod.extract_py_paths(description) == ["a/b.py"]


def test_emit_file_exists_adds_missing_path():
    description = "Create src/bob/brownfield/survey.py"
    criteria = ["Function defined: bob.brownfield.survey.run"]
    augmented, added = mod.emit_file_exists_acs(criteria, description)
    assert "src/bob/brownfield/survey.py" in added
    assert "File exists: src/bob/brownfield/survey.py" in augmented


def test_emit_file_exists_does_not_double_add():
    description = "Create src/bob/brownfield/survey.py"
    criteria = ["File exists: src/bob/brownfield/survey.py"]
    augmented, added = mod.emit_file_exists_acs(criteria, description)
    assert added == []
    assert augmented == criteria


def test_emit_file_exists_no_paths_is_noop():
    description = "A description with no concrete python paths at all."
    criteria = ["some ac"]
    augmented, added = mod.emit_file_exists_acs(criteria, description)
    assert added == []
    assert augmented == criteria
