"""Boundary tests for bob.include_graph_disjoint_gate.

Empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

from bob.include_graph_disjoint_gate import (
    check_disjoint_include_aware,
    flag_high_fanout_header,
)


def test_empty_edit_sites_are_disjoint():
    assert check_disjoint_include_aware({"edit_sites": []}, {"edit_sites": []}) is False


def test_missing_edit_sites_key_disjoint():
    assert check_disjoint_include_aware({}, {}) is False


def test_one_side_empty_disjoint():
    a = {"edit_sites": [{"path": "a.cpp", "start_line": 1, "end_line": 5}]}
    b = {"edit_sites": []}
    assert check_disjoint_include_aware(a, b) is False


def test_empty_include_graph_falls_back_to_path_overlap():
    a = {"edit_sites": [{"path": "a.cpp", "start_line": 1, "end_line": 5}]}
    b = {"edit_sites": [{"path": "b.cpp", "start_line": 1, "end_line": 5}]}
    assert check_disjoint_include_aware(a, b, include_graph={}) is False


def test_flag_high_fanout_empty_inputs():
    assert flag_high_fanout_header([]) == []
    assert flag_high_fanout_header([], include_graph={}) == []


def test_flag_high_fanout_no_graph_no_blast_radius():
    sites = [{"path": "x.h", "start_line": 1, "end_line": 5}]
    # No fan-out information available -> nothing flagged.
    assert flag_high_fanout_header(sites) == []
