"""Error-path tests: invalid input raises ValueError, no silent success."""

from __future__ import annotations

import pytest

from bob.cpp_stub_detector import detect_cpp_stubs, find_undefined_symbols


def test_detect_none_raises_value_error():
    with pytest.raises(ValueError):
        detect_cpp_stubs(None)


def test_detect_wrong_type_raises_value_error():
    with pytest.raises(ValueError):
        detect_cpp_stubs("not a dict")


def test_detect_non_string_key_raises_value_error():
    with pytest.raises(ValueError):
        detect_cpp_stubs({123: "void f(){}"})


def test_detect_non_string_value_raises_value_error():
    with pytest.raises(ValueError):
        detect_cpp_stubs({"a.cpp": 123})


def test_find_undefined_none_raises_value_error():
    with pytest.raises(ValueError):
        find_undefined_symbols(None)


def test_find_undefined_wrong_type_raises_value_error():
    with pytest.raises(ValueError):
        find_undefined_symbols("libfoo.so")


def test_find_undefined_non_string_element_raises_value_error():
    with pytest.raises(ValueError):
        find_undefined_symbols([123, 456])
