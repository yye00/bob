"""Tests for extract_class_name_from_criterion function."""

import pytest
from bob.verification.class_defined_ac_check import extract_class_name_from_criterion


def test_extracts_simple_class_name():
    result = extract_class_name_from_criterion("Class defined: bob.verification.mutation_gate.MutationReport")
    assert result == "MutationReport"


def test_extracts_deeply_nested_class_name():
    result = extract_class_name_from_criterion("Class defined: a.b.c.d.MyClass")
    assert result == "MyClass"


def test_extracts_top_level_class_name():
    result = extract_class_name_from_criterion("Class defined: MyClass")
    assert result == "MyClass"


def test_returns_none_for_non_matching_string():
    result = extract_class_name_from_criterion("Function defined: bob.verification.mutation_gate.some_func")
    assert result is None


def test_returns_none_for_empty_string():
    result = extract_class_name_from_criterion("")
    assert result is None


def test_returns_none_for_file_exists_criterion():
    result = extract_class_name_from_criterion("File exists: src/bob/verification/mutation_gate.py")
    assert result is None


def test_case_insensitive_prefix():
    result = extract_class_name_from_criterion("class defined: pkg.mod.Foo")
    assert result == "Foo"


def test_extracts_two_segment_path():
    result = extract_class_name_from_criterion("Class defined: mod.Bar")
    assert result == "Bar"
