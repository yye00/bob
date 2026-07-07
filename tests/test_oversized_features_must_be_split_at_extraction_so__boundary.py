"""Boundary/edge-case tests for bob.feature_splitter.

Verifies that empty, zero, or minimum inputs return well-defined results
rather than raising exceptions (boundary case AC).
"""

from __future__ import annotations

from bob.feature_splitter import (
    SplitRecommendation,
    pin_canonical_package,
    recommend_split,
)


def test_recommend_split_empty_acs_returns_no_split():
    """A feature with an empty AC list returns should_split=False, no raise."""
    rec = recommend_split({"name": "empty", "acceptance_criteria": []})
    assert isinstance(rec, SplitRecommendation)
    assert rec.should_split is False
    assert rec.num_modules == 0
    assert rec.num_entry_points == 0
    assert rec.sub_features == []


def test_recommend_split_missing_acs_key_returns_no_split():
    """A feature dict with no acceptance_criteria key is treated as empty."""
    rec = recommend_split({"name": "no-acs"})
    assert rec.should_split is False
    assert rec.num_entry_points == 0


def test_recommend_split_missing_name_uses_empty_string():
    """A feature dict with no name still returns a well-defined result."""
    rec = recommend_split({"acceptance_criteria": []})
    assert rec.feature_name == ""
    assert rec.should_split is False


def test_recommend_split_single_entry_point_no_split():
    """A single entry point (minimum non-empty case) is not split."""
    rec = recommend_split(
        {"name": "one", "acceptance_criteria": ["Function defined: hippy.a.f"]}
    )
    assert rec.should_split is False
    assert rec.num_entry_points == 1
    assert rec.num_modules == 1


def test_recommend_split_at_threshold_boundary():
    """Exactly 3 entry points across 2 modules meets the split threshold."""
    rec = recommend_split(
        {
            "name": "threshold",
            "acceptance_criteria": [
                "Function defined: hippy.a.f1",
                "Function defined: hippy.a.f2",
                "Function defined: hippy.b.g1",
            ],
        }
    )
    assert rec.num_modules == 2
    assert rec.num_entry_points == 3
    assert rec.should_split is True


def test_pin_empty_ac_list_returns_empty_list():
    """Pinning an empty AC list returns an empty list, no raise."""
    assert pin_canonical_package([], "hippy") == []


def test_pin_empty_acs_in_feature_dict():
    """Pinning a feature dict with empty ACs returns a copy with empty ACs."""
    out = pin_canonical_package({"name": "x", "acceptance_criteria": []}, "hippy")
    assert out["acceptance_criteria"] == []


def test_pin_missing_acs_key_treated_as_empty():
    """A feature dict with no acceptance_criteria key is treated as empty."""
    out = pin_canonical_package({"name": "x"}, "hippy")
    assert out["acceptance_criteria"] == []


def test_pin_non_structural_acs_only_pass_through():
    """A list of only pytest/CLI ACs is returned unchanged (minimum case)."""
    acs = ["pytest: tests/test_a.py", "CLI command: bob foo"]
    assert pin_canonical_package(acs, "hippy") == acs
