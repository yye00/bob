"""Error-path tests for bob.clang_ast_resolution (feature 43fbc3fb).

Invalid input must raise ValueError and the function must not silently succeed.
"""
from __future__ import annotations

import pytest

from bob.clang_ast_resolution import (
    probe_class_definition,
    probe_function_definition,
    search_for_class_clang,
    search_for_function_clang,
)


@pytest.mark.parametrize("bad_name", ["", "   ", "\t\n"])
def test_empty_function_name_raises(tmp_path, bad_name):
    with pytest.raises(ValueError):
        search_for_function_clang(tmp_path, bad_name)


@pytest.mark.parametrize("bad_name", ["", "   "])
def test_empty_class_name_raises(tmp_path, bad_name):
    with pytest.raises(ValueError):
        search_for_class_clang(tmp_path, bad_name)


@pytest.mark.parametrize("bad", [None, 123, ["foo"], {"a": 1}])
def test_non_string_function_name_raises(tmp_path, bad):
    with pytest.raises(ValueError):
        probe_function_definition(tmp_path, bad)


@pytest.mark.parametrize("bad", [None, 3.14, object()])
def test_non_string_class_name_raises(tmp_path, bad):
    with pytest.raises(ValueError):
        probe_class_definition(tmp_path, bad)


def test_none_workspace_raises():
    with pytest.raises(ValueError):
        search_for_function_clang(None, "foo")


def test_empty_workspace_path_raises():
    with pytest.raises(ValueError):
        search_for_class_clang("", "Widget")


@pytest.mark.parametrize("bad_ws", [123, ["/tmp"], {"p": "/tmp"}])
def test_non_pathlike_workspace_raises(bad_ws):
    with pytest.raises(ValueError):
        probe_function_definition(bad_ws, "foo")


def test_error_does_not_silently_succeed(tmp_path):
    """Confirm the error path raises rather than returning a truthy value."""
    raised = False
    try:
        search_for_function_clang(tmp_path, "")
    except ValueError:
        raised = True
    assert raised, "invalid input must raise ValueError, not silently succeed"
