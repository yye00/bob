"""Error-path tests (feature 80cd68f8).

Invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest

from bob.brownfield.coupled_edit_sites import (
    expand_coupled_edit_sites,
    derive_decl_end_line,
)


def test_none_symbol_raises():
    with pytest.raises(ValueError):
        expand_coupled_edit_sites(None)


def test_non_dict_symbol_raises():
    with pytest.raises(ValueError):
        expand_coupled_edit_sites(["not", "a", "dict"])


def test_symbol_missing_path_raises():
    with pytest.raises(ValueError):
        expand_coupled_edit_sites({"name": "f", "lineno": 1})


def test_symbol_missing_lineno_raises():
    with pytest.raises(ValueError):
        expand_coupled_edit_sites({"path": "a.cc", "name": "f"})


def test_negative_lineno_raises():
    with pytest.raises(ValueError):
        expand_coupled_edit_sites({"path": "a.cc", "name": "f", "lineno": -3})


def test_non_int_lineno_raises():
    with pytest.raises(ValueError):
        expand_coupled_edit_sites({"path": "a.cc", "name": "f", "lineno": "ten"})


def test_index_wrong_type_raises():
    with pytest.raises(ValueError):
        expand_coupled_edit_sites(
            {"path": "a.cc", "name": "f", "lineno": 1}, index=["bad"]
        )


def test_derive_decl_end_line_negative_start_raises():
    with pytest.raises(ValueError):
        derive_decl_end_line({}, start_line=-1)


def test_derive_decl_end_line_no_start_and_no_range_raises():
    with pytest.raises(ValueError):
        derive_decl_end_line({})
