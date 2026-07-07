"""Boundary tests: empty/zero/minimum input returns a well-defined result
rather than raising.
"""

from __future__ import annotations

from bob.scope_enumeration_linter import (
    ScopeEnumerationResult,
    check_scope_enumeration,
    has_unbounded_scope_word,
)


class TestBoundary:
    def test_empty_feature_dict_returns_ready_result(self):
        result = check_scope_enumeration({})
        assert isinstance(result, ScopeEnumerationResult)
        assert result.has_unbounded_scope is False
        assert result.is_ready is True

    def test_feature_with_empty_acceptance_criteria(self):
        feature = {"name": "x", "description": "add one number", "acceptance_criteria": []}
        result = check_scope_enumeration(feature)
        assert result.is_ready is True

    def test_empty_description_and_no_word(self):
        feature = {"name": "x", "description": "", "acceptance_criteria": []}
        result = check_scope_enumeration(feature)
        assert result.has_unbounded_scope is False
        assert result.is_ready is True

    def test_has_unbounded_scope_word_empty_string(self):
        assert has_unbounded_scope_word("") is None

    def test_spec_none_defaults_to_no_out_of_scope(self):
        feature = {
            "name": "big",
            "description": "comprehensive parity over the whole library API surface",
            "acceptance_criteria": ["Function defined: a.b", "Function defined: a.c"],
        }
        result = check_scope_enumeration(feature, spec=None)
        # No out-of-scope block anywhere -> not ready, but does not raise.
        assert result.is_ready is False
