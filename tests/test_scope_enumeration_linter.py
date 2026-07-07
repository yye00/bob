"""Tests for bob.scope_enumeration_linter.

The linter flags features that claim unbounded scope ("comprehensive", "full",
"complete", "everything", "100% parity") over a large API surface without an
explicit in-scope enumeration AND a spec-level out-of-scope block.
"""

from __future__ import annotations

import pytest

from bob.scope_enumeration_linter import (
    ScopeEnumerationResult,
    check_scope_enumeration,
    has_unbounded_scope_word,
)


class TestHasUnboundedScopeWord:
    def test_detects_comprehensive(self):
        assert has_unbounded_scope_word("comprehensive numpy parity") == "comprehensive"

    def test_detects_full(self):
        assert has_unbounded_scope_word("full scipy parity") == "full"

    def test_detects_complete(self):
        assert has_unbounded_scope_word("complete coverage of the API") == "complete"

    def test_detects_everything(self):
        assert has_unbounded_scope_word("port everything from numpy") == "everything"

    def test_detects_all_of_phrase(self):
        assert has_unbounded_scope_word("implement all of the linalg module") == "all of"

    def test_detects_100_percent_parity(self):
        assert has_unbounded_scope_word("achieve 100% parity") == "100% parity"

    def test_case_insensitive(self):
        assert has_unbounded_scope_word("COMPREHENSIVE support") == "comprehensive"

    def test_returns_none_when_bounded(self):
        assert has_unbounded_scope_word("add the sqrt function") is None

    def test_does_not_flag_plain_all(self):
        # "all" alone (not "all of") must not trigger — avoids false positives.
        assert has_unbounded_scope_word("returns all elements greater than x") is None

    def test_empty_string_returns_none(self):
        assert has_unbounded_scope_word("") is None


class TestCheckScopeEnumeration:
    def test_large_surface_unbounded_without_enumeration_flagged(self):
        feature = {
            "name": "NumPy parity",
            "description": "Provide comprehensive numpy parity across the whole library API surface.",
            "acceptance_criteria": ["pytest: tests/test_numpy.py"],
        }
        result = check_scope_enumeration(feature)
        assert isinstance(result, ScopeEnumerationResult)
        assert result.has_unbounded_scope is True
        assert result.requires_enumeration is True
        assert result.is_ready is False
        assert result.matched_word == "comprehensive"
        assert result.issues

    def test_large_surface_with_enumeration_and_out_of_scope_ready(self):
        feature = {
            "name": "NumPy parity",
            "description": "Provide comprehensive numpy parity over the library API surface.",
            "acceptance_criteria": [
                "Function defined: mylib.add",
                "Function defined: mylib.subtract",
                "Function defined: mylib.multiply",
            ],
        }
        spec = {"out_of_scope": ["numpy.fft", "numpy.random"]}
        result = check_scope_enumeration(feature, spec=spec)
        assert result.has_unbounded_scope is True
        assert result.requires_enumeration is True
        assert result.is_ready is True
        assert not result.issues

    def test_missing_out_of_scope_block_flagged(self):
        feature = {
            "name": "NumPy parity",
            "description": "Provide comprehensive numpy parity over the whole API surface.",
            "acceptance_criteria": [
                "Function defined: mylib.add",
                "Function defined: mylib.subtract",
            ],
        }
        result = check_scope_enumeration(feature, spec={})
        assert result.is_ready is False
        assert any("out-of-scope" in i.lower() for i in result.issues)

    def test_missing_enumeration_flagged(self):
        feature = {
            "name": "NumPy parity",
            "description": "Provide full parity for the entire numpy library API surface.",
            "acceptance_criteria": ["pytest: tests/test_numpy.py"],
        }
        result = check_scope_enumeration(feature, spec={"out_of_scope": ["fft"]})
        assert result.is_ready is False
        assert any("enumerat" in i.lower() for i in result.issues)

    def test_small_feature_single_function_not_flagged(self):
        # Boundary: unbounded word but small, naturally-complete surface.
        feature = {
            "name": "sqrt",
            "description": "Implement a complete sqrt function.",
            "acceptance_criteria": ["Function defined: mylib.sqrt"],
        }
        result = check_scope_enumeration(feature)
        assert result.requires_enumeration is False
        assert result.is_ready is True

    def test_no_unbounded_word_always_ready(self):
        feature = {
            "name": "add",
            "description": "Implement addition of two numbers.",
            "acceptance_criteria": ["Function defined: mylib.add"],
        }
        result = check_scope_enumeration(feature)
        assert result.has_unbounded_scope is False
        assert result.requires_enumeration is False
        assert result.is_ready is True

    def test_out_of_scope_detected_in_description_text(self):
        feature = {
            "name": "NumPy parity",
            "description": (
                "Provide comprehensive numpy parity over the API surface. "
                "Out-of-scope: fft, random, masked arrays."
            ),
            "acceptance_criteria": [
                "Function defined: mylib.add",
                "Function defined: mylib.subtract",
                "Function defined: mylib.multiply",
            ],
        }
        result = check_scope_enumeration(feature)
        assert result.is_ready is True

    def test_explicit_in_scope_line_counts_as_enumeration(self):
        feature = {
            "name": "NumPy parity",
            "description": (
                "Comprehensive numpy parity over the library API surface. "
                "In-scope: add, subtract, multiply, divide. "
                "Out-of-scope: fft, random."
            ),
            "acceptance_criteria": ["pytest: tests/test_numpy.py"],
        }
        result = check_scope_enumeration(feature)
        assert result.is_ready is True
