"""Tests for bob.include_graph_disjoint_gate.

Include-graph-aware disjointness gate for the coordinator. The base
check_disjoint only detects (path, line-range) overlap, which misses the
dominant C++ conflict mode: two features editing different .cpp files that
both #include (or both edit) the same header are compilation-coupled.
"""

from __future__ import annotations

import pytest

from bob.include_graph_disjoint_gate import (
    check_disjoint_include_aware,
    flag_high_fanout_header,
)


def _loc(sites):
    return {"edit_sites": sites}


def _site(path, start=1, end=10, name="", usr=None):
    s = {"path": path, "start_line": start, "end_line": end,
         "scope": "function", "name": name}
    if usr is not None:
        s["usr"] = usr
    return s


# ---------------------------------------------------------------------------
# Base line-range overlap still detected (backward compatible)
# ---------------------------------------------------------------------------

def test_line_range_overlap_same_file_conflicts():
    a = _loc([_site("a.cpp", 1, 20)])
    b = _loc([_site("a.cpp", 10, 30)])
    assert check_disjoint_include_aware(a, b) is True


def test_different_files_no_include_relation_disjoint():
    a = _loc([_site("a.cpp", 1, 20)])
    b = _loc([_site("b.cpp", 1, 20)])
    assert check_disjoint_include_aware(a, b) is False


# ---------------------------------------------------------------------------
# Same header touched by both -> conflict
# ---------------------------------------------------------------------------

def test_both_edit_same_header_conflicts():
    a = _loc([_site("rccl.h", 1, 5)])
    b = _loc([_site("rccl.h", 100, 120)])
    # different line ranges, but same header => compilation-coupled
    assert check_disjoint_include_aware(a, b) is True


def test_both_edit_different_headers_disjoint():
    a = _loc([_site("foo.h", 1, 5)])
    b = _loc([_site("bar.h", 1, 5)])
    assert check_disjoint_include_aware(a, b) is False


# ---------------------------------------------------------------------------
# One edits a header the other's TU includes -> conflict
# ---------------------------------------------------------------------------

def test_header_edit_vs_including_tu_conflicts():
    a = _loc([_site("rccl.h", 1, 5)])          # feature A edits the header
    b = _loc([_site("collectives.cpp", 40, 60)])  # feature B edits a TU
    graph = {"collectives.cpp": ["rccl.h", "other.h"]}
    assert check_disjoint_include_aware(a, b, include_graph=graph) is True


def test_header_edit_vs_non_including_tu_disjoint():
    a = _loc([_site("rccl.h", 1, 5)])
    b = _loc([_site("collectives.cpp", 40, 60)])
    graph = {"collectives.cpp": ["unrelated.h"]}
    assert check_disjoint_include_aware(a, b, include_graph=graph) is False


def test_include_relation_is_symmetric():
    a = _loc([_site("collectives.cpp", 40, 60)])
    b = _loc([_site("rccl.h", 1, 5)])
    graph = {"collectives.cpp": ["rccl.h"]}
    assert check_disjoint_include_aware(a, b, include_graph=graph) is True


# ---------------------------------------------------------------------------
# Same USR, different definitions -> conflict
# ---------------------------------------------------------------------------

def test_same_usr_different_definition_conflicts():
    a = _loc([_site("a.cpp", 1, 5, usr="c:@F@ncclAllReduce")])
    b = _loc([_site("b.cpp", 1, 5, usr="c:@F@ncclAllReduce")])
    assert check_disjoint_include_aware(a, b) is True


def test_different_usr_disjoint():
    a = _loc([_site("a.cpp", 1, 5, usr="c:@F@foo")])
    b = _loc([_site("b.cpp", 1, 5, usr="c:@F@bar")])
    assert check_disjoint_include_aware(a, b) is False


# ---------------------------------------------------------------------------
# header_impl_pairs coupling
# ---------------------------------------------------------------------------

def test_header_impl_pair_conflicts():
    a = _loc([_site("net.h", 1, 5)])
    b = _loc([_site("net.cpp", 40, 60)])
    pairs = {"net.h": "net.cpp"}
    assert check_disjoint_include_aware(a, b, header_impl_pairs=pairs) is True


# ---------------------------------------------------------------------------
# flag_high_fanout_header
# ---------------------------------------------------------------------------

def test_flag_high_fanout_header_flags_core_header():
    sites = [_site("rccl.h", 1, 5)]
    graph = {
        "a.cpp": ["rccl.h"],
        "b.cpp": ["rccl.h"],
        "c.cpp": ["rccl.h"],
        "d.cpp": ["rccl.h"],
        "e.cpp": ["rccl.h"],
    }
    flagged = flag_high_fanout_header(sites, include_graph=graph, threshold=3)
    assert any(f["path"] == "rccl.h" for f in flagged)
    entry = next(f for f in flagged if f["path"] == "rccl.h")
    assert entry["fanout"] == 5
    assert entry["single_threaded"] is True


def test_flag_high_fanout_header_below_threshold_not_flagged():
    sites = [_site("small.h", 1, 5)]
    graph = {"a.cpp": ["small.h"]}
    flagged = flag_high_fanout_header(sites, include_graph=graph, threshold=3)
    assert flagged == []


def test_flag_high_fanout_ignores_non_headers():
    sites = [_site("impl.cpp", 1, 5)]
    graph = {"a.cpp": ["impl.cpp"]}  # nonsensical but should be ignored (cpp not header)
    flagged = flag_high_fanout_header(sites, include_graph=graph, threshold=1)
    assert flagged == []


def test_flag_high_fanout_uses_blast_radius_override():
    sites = [_site("core.h", 1, 5)]
    flagged = flag_high_fanout_header(
        sites, blast_radius={"core.h": 42}, threshold=10
    )
    assert len(flagged) == 1
    assert flagged[0]["fanout"] == 42


def test_flag_high_fanout_empty_sites_returns_empty():
    assert flag_high_fanout_header([]) == []
