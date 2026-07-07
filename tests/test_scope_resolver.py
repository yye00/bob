"""Tests for hippy.scope_resolver — extraction-time unbounded-scope gate."""

from __future__ import annotations

import pytest

from hippy.scope_resolver import (
    ScopeEnumerationResult,
    flag_unbounded_scope,
    has_unbounded_scope_word,
    resolve_scope_enumeration,
)


class TestResolveScopeEnumeration:
    def test_bounded_feature_is_ready(self):
        feature = {
            "name": "add",
            "description": "add two numbers",
            "acceptance_criteria": ["Function defined: m.add"],
        }
        result = resolve_scope_enumeration(feature)
        assert isinstance(result, ScopeEnumerationResult)
        assert result.has_unbounded_scope is False
        assert result.is_ready is True

    def test_unbounded_large_surface_without_enumeration_flagged(self):
        feature = {
            "name": "parity",
            "description": "comprehensive parity over the whole numpy library API surface",
            "acceptance_criteria": ["Function defined: np.add"],
        }
        result = resolve_scope_enumeration(feature)
        assert result.has_unbounded_scope is True
        assert result.requires_enumeration is True
        assert result.is_ready is False
        assert result.issues

    def test_unbounded_with_enumeration_and_out_of_scope_ready(self):
        feature = {
            "name": "parity",
            "description": "comprehensive parity over the numpy library API surface",
            "acceptance_criteria": [
                "Function defined: np.add",
                "Function defined: np.sub",
                "Function defined: np.mul",
                "Out-of-scope: fft, linalg deferred to a later feature",
            ],
        }
        result = resolve_scope_enumeration(feature)
        assert result.has_unbounded_scope is True
        assert result.is_ready is True
        assert result.issues == []

    def test_out_of_scope_via_spec_dict(self):
        feature = {
            "name": "parity",
            "description": "full parity over the numpy library",
            "acceptance_criteria": [
                "Function defined: np.add",
                "Function defined: np.sub",
                "Function defined: np.mul",
            ],
        }
        spec = {"out_of_scope": ["fft", "linalg"]}
        result = resolve_scope_enumeration(feature, spec=spec)
        assert result.is_ready is True

    def test_small_unbounded_feature_not_flagged(self):
        feature = {
            "name": "clip",
            "description": "complete implementation of clip",
            "acceptance_criteria": ["Function defined: m.clip"],
        }
        result = resolve_scope_enumeration(feature)
        assert result.has_unbounded_scope is True
        assert result.requires_enumeration is False
        assert result.is_ready is True


class TestFlagUnboundedScope:
    def test_returns_empty_for_bounded(self):
        feature = {
            "name": "add",
            "description": "add two numbers",
            "acceptance_criteria": ["Function defined: m.add"],
        }
        assert flag_unbounded_scope(feature) == []

    def test_returns_issues_for_unbounded_large_surface(self):
        feature = {
            "name": "parity",
            "description": "comprehensive parity over the entire library API surface",
            "acceptance_criteria": ["Function defined: np.add"],
        }
        issues = flag_unbounded_scope(feature)
        assert issues
        assert any("comprehensive" in i for i in issues)


class TestHasUnboundedScopeWord:
    def test_detects_comprehensive(self):
        assert has_unbounded_scope_word("comprehensive parity") == "comprehensive"

    def test_returns_none_when_bounded(self):
        assert has_unbounded_scope_word("add two numbers") is None


class TestErrorPaths:
    def test_non_dict_feature_raises(self):
        with pytest.raises((ValueError, TypeError)):
            resolve_scope_enumeration("comprehensive")  # type: ignore[arg-type]

    def test_flag_non_dict_raises(self):
        with pytest.raises((ValueError, TypeError)):
            flag_unbounded_scope(None)  # type: ignore[arg-type]

    def test_invalid_spec_raises(self):
        feature = {
            "name": "x",
            "description": "comprehensive parity over the API surface",
            "acceptance_criteria": ["Function defined: a.b"],
        }
        with pytest.raises((ValueError, TypeError)):
            resolve_scope_enumeration(feature, spec="nope")  # type: ignore[arg-type]

    def test_has_unbounded_scope_word_non_str_raises(self):
        with pytest.raises((ValueError, TypeError)):
            has_unbounded_scope_word(123)  # type: ignore[arg-type]


class TestIntegration:
    def test_spec_extractor_reexports_resolver(self):
        import hippy.spec_extractor as se

        assert hasattr(se, "resolve_scope_enumeration")
        assert hasattr(se, "flag_unbounded_scope")
