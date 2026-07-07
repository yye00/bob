"""Boundary tests for bob.header_impl_pairing.

Empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

import json
from pathlib import Path

from bob import header_impl_pairing as hip


def test_build_include_graph_empty_project(tmp_path):
    # no compile_commands.json, no sources — well-defined empty graph
    graph = hip.build_include_graph(tmp_path)
    assert graph == {}


def test_build_include_graph_empty_compile_commands(tmp_path):
    (tmp_path / "compile_commands.json").write_text("[]")
    graph = hip.build_include_graph(tmp_path)
    assert isinstance(graph, dict)
    assert graph == {}


def test_compute_blast_radius_empty_graph_zero():
    assert hip.compute_blast_radius({}, "anything.h") == 0


def test_compute_blast_radius_node_absent_zero():
    graph = {"a.cpp": ["a.h"], "a.h": []}
    # node not present in graph -> zero, not a KeyError
    assert hip.compute_blast_radius(graph, "missing.h") == 0


def test_pair_header_impl_empty_list():
    assert hip.pair_header_impl([]) == []


def test_switch_source_header_empty_candidates():
    assert hip.switch_source_header("foo.cpp", []) is None


def test_single_file_include_graph(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    (root / "solo.cpp").write_text("int main(){return 0;}\n")
    cc = [{"directory": str(root), "file": str(root / "solo.cpp"),
           "command": f"c++ -c {root / 'solo.cpp'}"}]
    (root / "compile_commands.json").write_text(json.dumps(cc))
    graph = hip.build_include_graph(root)
    solo = next(k for k in graph if Path(k).name == "solo.cpp")
    assert graph[solo] == []
    assert hip.compute_blast_radius(graph, solo) == 0
