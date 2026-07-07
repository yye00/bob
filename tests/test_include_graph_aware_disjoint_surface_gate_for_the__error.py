"""Error-path tests for bob.include_graph_disjoint_gate.

Invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest

from bob.include_graph_disjoint_gate import (
    check_disjoint_include_aware,
    flag_high_fanout_header,
)


def test_non_dict_loc_a_raises():
    with pytest.raises(ValueError):
        check_disjoint_include_aware("not a dict", {"edit_sites": []})


def test_non_dict_loc_b_raises():
    with pytest.raises(ValueError):
        check_disjoint_include_aware({"edit_sites": []}, None)


def test_include_graph_wrong_type_raises():
    a = {"edit_sites": []}
    b = {"edit_sites": []}
    with pytest.raises(ValueError):
        check_disjoint_include_aware(a, b, include_graph="not a dict")


def test_header_impl_pairs_wrong_type_raises():
    a = {"edit_sites": []}
    b = {"edit_sites": []}
    with pytest.raises(ValueError):
        check_disjoint_include_aware(a, b, header_impl_pairs=[1, 2, 3])


def test_flag_high_fanout_non_list_sites_raises():
    with pytest.raises(ValueError):
        flag_high_fanout_header("not a list")


def test_flag_high_fanout_bad_include_graph_raises():
    with pytest.raises(ValueError):
        flag_high_fanout_header([], include_graph="nope")


def test_flag_high_fanout_negative_threshold_raises():
    with pytest.raises(ValueError):
        flag_high_fanout_header([], threshold=-1)
