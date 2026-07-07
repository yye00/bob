"""Tests for tools.spec_quality_score._is_code_identifier.

The contract_completeness sub-metric extracts candidate API surfaces from a
feature description and requires each to be covered by an acceptance criterion.
A description that writes a template like ``def NAME(...)`` or references
``NAME`` as a placeholder must NOT have ``NAME`` treated as a real symbol —
all-caps tokens are prose emphasis / placeholders, not code identifiers.
"""
import importlib

import pytest

from tools.spec_quality_score import _is_code_identifier


def test_all_caps_placeholders_are_rejected():
    for token in ("NAME", "FOO", "TODO", "BAR", "VALUE"):
        assert _is_code_identifier(token) is False, token


def test_all_caps_with_underscore_is_rejected():
    # UPPER_SNAKE like NAME/TODO emphasis is prose, not a required symbol.
    assert _is_code_identifier("FOO_BAR") is False


def test_pluralised_acronyms_are_rejected():
    for token in ("ACs", "IDs", "URLs"):
        assert _is_code_identifier(token) is False, token


def test_bare_acronym_is_rejected():
    assert _is_code_identifier("API") is False
    assert _is_code_identifier("HTTP") is False


def test_camelcase_requires_both_upper_and_lower():
    # Genuine CamelCase symbols must be accepted.
    assert _is_code_identifier("RetryCounter") is True
    assert _is_code_identifier("HTTPServer") is True


def test_snake_case_and_dotted_symbols_accepted():
    assert _is_code_identifier("my_func") is True
    assert _is_code_identifier("module.attr") is True
    assert _is_code_identifier("script.py") is True


def test_plain_english_words_are_rejected():
    for token in ("defined", "name", "gate", "correctly"):
        assert _is_code_identifier(token) is False, token


def test_empty_string_is_rejected():
    assert _is_code_identifier("") is False


def test_integration_placeholder_not_extracted_as_surface():
    # End-to-end: a description using "def NAME(...)" as a template must not
    # surface NAME as a real API requiring AC coverage.
    mod = importlib.import_module("tools.spec_quality_score")
    assert mod._is_code_identifier("NAME") is False
