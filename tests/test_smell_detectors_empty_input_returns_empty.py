"""Tests that detect_all([]) / detect_all("") return empty list — zero-element boundary."""

from __future__ import annotations

import pytest

from bob.spec_quality.smell_detectors import detect_all


class TestDetectAllEmptyInput:
    def test_empty_string_returns_empty_list(self):
        result = detect_all("")
        assert result == []

    def test_whitespace_only_returns_empty_or_list(self):
        result = detect_all("   ")
        assert isinstance(result, list)

    def test_empty_list_of_criteria_returns_empty(self):
        """Passing an empty peer_criteria list still works; empty text → empty."""
        result = detect_all("", peer_criteria=[])
        assert result == []

    def test_return_type_is_list_for_empty_string(self):
        result = detect_all("")
        assert isinstance(result, list)

    def test_empty_string_with_empty_known_ids_returns_empty(self):
        result = detect_all("", known_feature_ids=frozenset())
        assert result == []
