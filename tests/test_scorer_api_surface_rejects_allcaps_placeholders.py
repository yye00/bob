"""Behaviour test for feature e624b138: the scorer's API-surface detection
MUST reject all-caps prose placeholders.

WHEN the scorer extracts API surfaces from a description THEN all-caps
placeholder tokens (NAME, FOO, TODO) MUST NOT be treated as real symbols
requiring AC coverage. CamelCase must contain BOTH an uppercase and a
lowercase letter to qualify (so RetryCounter qualifies but NAME/acronyms
do not).
"""
import importlib

import pytest

mod = importlib.import_module("tools.spec_quality_score")
_is_code_identifier = mod._is_code_identifier


@pytest.mark.parametrize("placeholder", ["NAME", "FOO", "TODO", "BAR", "XXX", "UPPER_CASE"])
def test_all_caps_placeholders_rejected(placeholder):
    assert _is_code_identifier(placeholder) is False


@pytest.mark.parametrize("acronym", ["ACs", "IDs", "URLs"])
def test_pluralised_acronyms_rejected(acronym):
    assert _is_code_identifier(acronym) is False


@pytest.mark.parametrize("symbol", ["RetryCounter", "spec_quality_score", "module.func", "widget.py"])
def test_real_symbols_accepted(symbol):
    assert _is_code_identifier(symbol) is True


@pytest.mark.parametrize("word", ["defined", "name", "gate", "correctly"])
def test_plain_english_words_rejected(word):
    assert _is_code_identifier(word) is False


def test_def_name_template_not_extracted_as_surface():
    """The regression: a 'def NAME(...)' template referencing NAME as a
    placeholder must not surface NAME as a real API symbol."""
    assert _is_code_identifier("NAME") is False
