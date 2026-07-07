"""Boundary-case tests (feature 80cd68f8).

Empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

from bob.brownfield.coupled_edit_sites import (
    expand_coupled_edit_sites,
    derive_decl_end_line,
)


def test_minimal_symbol_no_index_returns_single_uncoupled_site():
    sym = {"path": "a.cc", "name": "f", "lineno": 1}
    group = expand_coupled_edit_sites(sym)
    assert group["coupled"] is False
    assert len(group["sites"]) == 1


def test_empty_index_behaves_like_no_index():
    sym = {"path": "a.cc", "name": "f", "lineno": 1, "usr": "u"}
    group = expand_coupled_edit_sites(sym, index={})
    assert group["coupled"] is False
    assert len(group["sites"]) == 1


def test_symbol_at_line_one_returns_well_defined_end_line():
    sym = {"path": "a.cc", "name": "f", "lineno": 1}
    group = expand_coupled_edit_sites(sym, fallback_span=0)
    assert group["sites"][0]["start_line"] == 1
    assert group["sites"][0]["end_line"] == 1


def test_index_entry_with_no_overrides_still_returns_group():
    index = {"u": {
        "declaration": {"path": "h.h", "lineno": 2, "range": {"end": {"line": 2}}},
        "definition": {"path": "c.cc", "lineno": 10, "range": {"end": {"line": 20}}},
    }}
    sym = {"path": "c.cc", "name": "f", "lineno": 10, "usr": "u"}
    group = expand_coupled_edit_sites(sym, index=index)
    assert group["coupled"] is True
    assert len(group["sites"]) == 2


def test_derive_end_line_with_empty_decl_uses_fallback():
    assert derive_decl_end_line({}, start_line=1, fallback_span=0) == 1


def test_no_matching_index_entry_returns_uncoupled():
    index = {"other": {"definition": {"path": "x.cc", "lineno": 1}}}
    sym = {"path": "a.cc", "name": "f", "lineno": 1, "usr": "u"}
    group = expand_coupled_edit_sites(sym, index=index)
    assert group["coupled"] is False
    assert len(group["sites"]) == 1
