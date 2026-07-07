"""Tests for bob.header_impl_pairing — header/impl pairing + include blast-radius graph.

Feature bd36773c: C++ splits one logical symbol across a declaration in a header
and a definition in an implementation file.  This module models:
  1. header<->source pairing (clangd switchSourceHeader heuristic),
  2. a preprocessor #include graph resolved through -I paths in compile_commands.json,
  3. a per-symbol/per-header blast-radius score (downstream TUs reachable via includes).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bob import header_impl_pairing as hip


# ---------------------------------------------------------------------------
# Fixtures — a tiny C++ project tree
# ---------------------------------------------------------------------------
def _make_project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    inc = root / "include"
    src = root / "src"
    inc.mkdir(parents=True)
    src.mkdir(parents=True)

    (inc / "rccl.h").write_text("#pragma once\nint rccl_init();\n")
    (inc / "util.h").write_text('#pragma once\n#include "rccl.h"\nint helper();\n')

    (src / "rccl.cpp").write_text('#include "rccl.h"\nint rccl_init() { return 0; }\n')
    (src / "util.cpp").write_text('#include "util.h"\nint helper() { return rccl_init(); }\n')
    (src / "main.cpp").write_text('#include "util.h"\nint main() { return helper(); }\n')

    compile_commands = [
        {
            "directory": str(src),
            "file": str(src / "rccl.cpp"),
            "command": f"c++ -I{inc} -c {src / 'rccl.cpp'}",
        },
        {
            "directory": str(src),
            "file": str(src / "util.cpp"),
            "command": f"c++ -I{inc} -c {src / 'util.cpp'}",
        },
        {
            "directory": str(src),
            "file": str(src / "main.cpp"),
            "command": f"c++ -I{inc} -c {src / 'main.cpp'}",
        },
    ]
    (root / "compile_commands.json").write_text(json.dumps(compile_commands))
    return root


# ---------------------------------------------------------------------------
# build_include_graph
# ---------------------------------------------------------------------------
def test_build_include_graph_returns_edges(tmp_path):
    root = _make_project(tmp_path)
    graph = hip.build_include_graph(root)
    assert isinstance(graph, dict)
    # every source/header file should be a node
    names = {Path(k).name for k in graph}
    assert {"rccl.cpp", "util.cpp", "main.cpp", "util.h", "rccl.h"} <= names


def test_build_include_graph_resolves_quoted_include(tmp_path):
    root = _make_project(tmp_path)
    graph = hip.build_include_graph(root)
    # util.cpp includes util.h
    util_cpp = next(k for k in graph if Path(k).name == "util.cpp")
    included_names = {Path(x).name for x in graph[util_cpp]}
    assert "util.h" in included_names


def test_build_include_graph_resolves_via_dash_I(tmp_path):
    root = _make_project(tmp_path)
    graph = hip.build_include_graph(root)
    # util.h includes rccl.h, which lives in include/ resolved via -I
    util_h = next(k for k in graph if Path(k).name == "util.h")
    included_names = {Path(x).name for x in graph[util_h]}
    assert "rccl.h" in included_names


def test_build_include_graph_accepts_explicit_compile_commands(tmp_path):
    root = _make_project(tmp_path)
    cc = root / "compile_commands.json"
    graph = hip.build_include_graph(root, compile_commands=cc)
    assert graph  # non-empty


# ---------------------------------------------------------------------------
# compute_blast_radius
# ---------------------------------------------------------------------------
def test_compute_blast_radius_core_header_high(tmp_path):
    root = _make_project(tmp_path)
    graph = hip.build_include_graph(root)
    rccl_h = next(k for k in graph if Path(k).name == "rccl.h")
    # rccl.h is transitively included by rccl.cpp, util.cpp, main.cpp (all TUs)
    radius = hip.compute_blast_radius(graph, rccl_h)
    assert isinstance(radius, int)
    assert radius >= 3


def test_compute_blast_radius_local_header_low(tmp_path):
    root = _make_project(tmp_path)
    graph = hip.build_include_graph(root)
    util_h = next(k for k in graph if Path(k).name == "util.h")
    rccl_h = next(k for k in graph if Path(k).name == "rccl.h")
    # util.h reaches util.cpp + main.cpp (2 TUs); strictly fewer than rccl.h
    util_radius = hip.compute_blast_radius(graph, util_h)
    rccl_radius = hip.compute_blast_radius(graph, rccl_h)
    assert util_radius < rccl_radius


def test_compute_blast_radius_leaf_source_zero(tmp_path):
    root = _make_project(tmp_path)
    graph = hip.build_include_graph(root)
    main_cpp = next(k for k in graph if Path(k).name == "main.cpp")
    # nothing includes main.cpp
    assert hip.compute_blast_radius(graph, main_cpp) == 0


# ---------------------------------------------------------------------------
# header/impl pairing
# ---------------------------------------------------------------------------
def test_is_header_and_is_impl():
    assert hip.is_header("foo/bar.h")
    assert hip.is_header("foo/bar.hpp")
    assert hip.is_header("foo/bar.cuh")
    assert not hip.is_header("foo/bar.cpp")
    assert hip.is_impl("foo/bar.cpp")
    assert hip.is_impl("foo/bar.cc")
    assert hip.is_impl("foo/bar.hip")
    assert not hip.is_impl("foo/bar.h")


def test_switch_source_header_pairs_by_stem(tmp_path):
    root = _make_project(tmp_path)
    files = [str(p) for p in root.rglob("*") if p.is_file() and p.suffix in {".h", ".hpp", ".cuh", ".cpp", ".cc", ".hip"}]
    rccl_cpp = next(f for f in files if Path(f).name == "rccl.cpp")
    paired = hip.switch_source_header(rccl_cpp, files)
    assert paired is not None
    assert Path(paired).name == "rccl.h"


def test_switch_source_header_no_pair_returns_none(tmp_path):
    root = _make_project(tmp_path)
    files = [str(p) for p in root.rglob("*") if p.is_file()]
    main_cpp = next(f for f in files if Path(f).name == "main.cpp")
    # there is no main.h
    assert hip.switch_source_header(main_cpp, files) is None


def test_pair_header_impl_lists_matched_pairs(tmp_path):
    root = _make_project(tmp_path)
    files = [str(p) for p in root.rglob("*") if p.is_file()]
    pairs = hip.pair_header_impl(files)
    assert isinstance(pairs, list)
    stems = {(Path(h).name, Path(i).name) for h, i in pairs}
    assert ("rccl.h", "rccl.cpp") in stems
