"""Boundary tests: empty/zero/minimum input returns a well-defined result."""

from __future__ import annotations

from bob.cpp_stub_detector import detect_cpp_stubs, find_undefined_symbols


def test_detect_empty_dict_returns_empty_list():
    assert detect_cpp_stubs({}) == []


def test_detect_empty_source_string_returns_empty_list():
    assert detect_cpp_stubs({"a.cpp": ""}) == []


def test_detect_whitespace_only_source_returns_empty_list():
    assert detect_cpp_stubs({"a.cpp": "   \n\t\n"}) == []


def test_detect_only_non_native_files_returns_empty_list():
    assert detect_cpp_stubs({"a.py": "x=1", "b.txt": "hello"}) == []


def test_find_undefined_symbols_empty_list_returns_empty():
    assert find_undefined_symbols([]) == []


def test_find_undefined_symbols_nonexistent_paths_returns_empty():
    assert find_undefined_symbols(["/no/such/file.o", "/also/missing.so"]) == []


def test_detect_returns_list_type():
    assert isinstance(detect_cpp_stubs({}), list)


def test_find_undefined_returns_list_type():
    assert isinstance(find_undefined_symbols([]), list)
