"""Tests: before_after_same_test_set handles empty/boundary snapshot sets."""

from __future__ import annotations

import pytest

from bob3.verifier.snapshot import before_after_same_test_set


class TestBeforeAfterSameTestSetBoundary:
    """before_after_same_test_set returns True when both before/after sets are empty."""

    def test_both_empty_returns_true(self):
        assert before_after_same_test_set({}, {}) is True

    def test_before_empty_after_nonempty_returns_false(self):
        assert before_after_same_test_set({}, {"tests/t.py::test_a": True}) is False

    def test_before_nonempty_after_empty_returns_false(self):
        assert before_after_same_test_set({"tests/t.py::test_a": True}, {}) is False

    def test_identical_single_test_returns_true(self):
        snap = {"tests/t.py::test_a": True}
        assert before_after_same_test_set(snap, snap) is True

    def test_same_keys_different_values_returns_true(self):
        before = {"tests/t.py::test_a": True, "tests/t.py::test_b": True}
        after = {"tests/t.py::test_a": False, "tests/t.py::test_b": True}
        assert before_after_same_test_set(before, after) is True

    def test_different_keys_returns_false(self):
        before = {"tests/t.py::test_a": True}
        after = {"tests/t.py::test_b": True}
        assert before_after_same_test_set(before, after) is False

    def test_subset_returns_false(self):
        before = {"tests/t.py::test_a": True, "tests/t.py::test_b": False}
        after = {"tests/t.py::test_a": True}
        assert before_after_same_test_set(before, after) is False

    def test_large_identical_sets_return_true(self):
        large = {f"tests/t.py::test_{i}": (i % 2 == 0) for i in range(100)}
        assert before_after_same_test_set(large, large) is True
