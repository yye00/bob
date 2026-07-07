"""Error-path tests for bob.header_impl_pairing.

Invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest

from bob import header_impl_pairing as hip


def test_build_include_graph_none_root():
    with pytest.raises(ValueError):
        hip.build_include_graph(None)


def test_build_include_graph_non_path_type():
    with pytest.raises(ValueError):
        hip.build_include_graph(12345)


def test_build_include_graph_missing_explicit_compile_commands(tmp_path):
    with pytest.raises(ValueError):
        hip.build_include_graph(tmp_path, compile_commands=tmp_path / "does_not_exist.json")


def test_build_include_graph_malformed_compile_commands(tmp_path):
    (tmp_path / "compile_commands.json").write_text("{ this is not json ]")
    with pytest.raises(ValueError):
        hip.build_include_graph(tmp_path)


def test_compute_blast_radius_none_graph():
    with pytest.raises(ValueError):
        hip.compute_blast_radius(None, "a.h")


def test_compute_blast_radius_non_dict_graph():
    with pytest.raises(ValueError):
        hip.compute_blast_radius(["not", "a", "dict"], "a.h")


def test_compute_blast_radius_empty_node():
    with pytest.raises(ValueError):
        hip.compute_blast_radius({"a.h": []}, "")


def test_compute_blast_radius_none_node():
    with pytest.raises(ValueError):
        hip.compute_blast_radius({"a.h": []}, None)


def test_pair_header_impl_non_list():
    with pytest.raises(ValueError):
        hip.pair_header_impl("not-a-list")


def test_switch_source_header_none_target():
    with pytest.raises(ValueError):
        hip.switch_source_header(None, ["a.h"])
