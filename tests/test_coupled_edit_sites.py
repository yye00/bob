"""Feature 80cd68f8 — Cross-TU coupled edit-site localization.

Given a localized C++ symbol, expand one logical change into the full set of
coupled edit-sites: the header declaration, the .cc/.hip definition, and every
overriding definition — deriving accurate end_line from clang's decl source
range instead of the +20 heuristic.
"""

from __future__ import annotations

import pytest

from bob.brownfield.coupled_edit_sites import (
    expand_coupled_edit_sites,
    derive_decl_end_line,
)


# ---------------------------------------------------------------------------
# derive_decl_end_line
# ---------------------------------------------------------------------------


def test_derive_end_line_from_explicit_end_line():
    assert derive_decl_end_line({"end_line": 42}, start_line=10) == 42


def test_derive_end_line_from_clang_extent_range():
    decl = {"range": {"end": {"line": 88}}}
    assert derive_decl_end_line(decl, start_line=80) == 88


def test_derive_end_line_from_extent_key():
    decl = {"extent": {"end": {"line": 55}}}
    assert derive_decl_end_line(decl, start_line=50) == 55


def test_derive_end_line_falls_back_to_span_when_range_absent():
    # No clang range → fall back to start_line + span (the legacy heuristic).
    assert derive_decl_end_line({}, start_line=100, fallback_span=20) == 120


def test_derive_end_line_never_less_than_start():
    # A malformed range that would put end before start clamps to start.
    assert derive_decl_end_line({"end_line": 5}, start_line=30) == 30


def test_derive_end_line_uses_decl_begin_line_when_start_absent():
    decl = {"range": {"begin": {"line": 12}, "end": {"line": 20}}}
    assert derive_decl_end_line(decl) == 20


# ---------------------------------------------------------------------------
# expand_coupled_edit_sites — single site (no index / no matches)
# ---------------------------------------------------------------------------


def test_expand_single_symbol_no_index_returns_one_site():
    sym = {"path": "src/foo.cc", "name": "Foo::bar", "lineno": 10, "end_lineno": 20,
           "kind": "method"}
    group = expand_coupled_edit_sites(sym)
    assert group["coupled"] is False
    assert len(group["sites"]) == 1
    site = group["sites"][0]
    assert site["path"] == "src/foo.cc"
    assert site["start_line"] == 10
    assert site["end_line"] == 20
    assert site["role"] == "definition"


def test_expand_single_symbol_uses_derive_when_end_missing():
    sym = {"path": "src/foo.cc", "name": "bar", "lineno": 5, "kind": "function"}
    group = expand_coupled_edit_sites(sym, fallback_span=20)
    assert group["sites"][0]["end_line"] == 25


# ---------------------------------------------------------------------------
# expand_coupled_edit_sites — full coupled group
# ---------------------------------------------------------------------------


def _index_with_decl_def_overrides():
    return {
        "c:@S@Op@F@run#": {
            "declaration": {
                "path": "include/op.h",
                "lineno": 12,
                "range": {"end": {"line": 12}},
            },
            "definition": {
                "path": "src/op.cc",
                "lineno": 40,
                "range": {"end": {"line": 58}},
            },
            "overrides": [
                {"path": "src/op_gpu.hip", "lineno": 100,
                 "range": {"end": {"line": 130}}},
                {"path": "src/op_cpu.cc", "lineno": 5,
                 "range": {"end": {"line": 22}}},
            ],
        }
    }


def test_expand_produces_declaration_definition_and_overrides():
    sym = {"path": "src/op.cc", "name": "Op::run", "usr": "c:@S@Op@F@run#",
           "lineno": 40, "kind": "method"}
    group = expand_coupled_edit_sites(sym, index=_index_with_decl_def_overrides())

    assert group["coupled"] is True
    assert group["requires_coordinated_edit"] is True

    roles = [s["role"] for s in group["sites"]]
    assert "declaration" in roles
    assert "definition" in roles
    assert roles.count("override") == 2

    # Header declaration is present and end_line derived from clang range.
    decl = next(s for s in group["sites"] if s["role"] == "declaration")
    assert decl["path"] == "include/op.h"
    assert decl["start_line"] == 12
    assert decl["end_line"] == 12

    # .hip override end_line derived from range, not +20.
    hip = next(s for s in group["sites"] if s["path"] == "src/op_gpu.hip")
    assert hip["end_line"] == 130
    assert hip["role"] == "override"


def test_expand_matches_by_name_when_usr_absent():
    index = {"Widget::draw": {
        "declaration": {"path": "widget.h", "lineno": 3, "range": {"end": {"line": 3}}},
        "definition": {"path": "widget.cc", "lineno": 20, "range": {"end": {"line": 40}}},
    }}
    sym = {"path": "widget.cc", "name": "Widget::draw", "lineno": 20, "kind": "method"}
    group = expand_coupled_edit_sites(sym, index=index)
    assert group["coupled"] is True
    assert {s["role"] for s in group["sites"]} == {"declaration", "definition"}


def test_expand_all_sites_carry_group_id():
    sym = {"path": "src/op.cc", "name": "Op::run", "usr": "c:@S@Op@F@run#",
           "lineno": 40, "kind": "method"}
    group = expand_coupled_edit_sites(sym, index=_index_with_decl_def_overrides())
    gid = group["group_id"]
    assert gid
    assert all(s["group_id"] == gid for s in group["sites"])


def test_expand_deduplicates_identical_declaration_and_definition():
    # Header-only inline symbol: decl and def at same path/line → single site.
    index = {"Inline::f": {
        "declaration": {"path": "inl.h", "lineno": 7, "range": {"end": {"line": 9}}},
        "definition": {"path": "inl.h", "lineno": 7, "range": {"end": {"line": 9}}},
    }}
    sym = {"path": "inl.h", "name": "Inline::f", "lineno": 7, "kind": "method"}
    group = expand_coupled_edit_sites(sym, index=index)
    assert len(group["sites"]) == 1


def test_expand_returns_serializable_dict():
    import json
    sym = {"path": "src/op.cc", "name": "Op::run", "usr": "c:@S@Op@F@run#",
           "lineno": 40, "kind": "method"}
    group = expand_coupled_edit_sites(sym, index=_index_with_decl_def_overrides())
    json.dumps(group)  # must not raise
