"""Boundary tests for validate_regression_ownership (feature 22356d3b-f0c3-408f-9dd8-23ad03333e43).

Verifies that empty, zero, or minimum inputs return well-defined results
rather than raising exceptions.
"""

from __future__ import annotations

from bob3.regression_detection import validate_regression_ownership


def test_both_empty_sets_returns_false_no_exception():
    """Empty owned_files and empty breaking_files → (False, []) without raising."""
    has_ev, evidence = validate_regression_ownership(
        feature_id="feat-boundary",
        owned_files=set(),
        breaking_files=set(),
    )
    assert has_ev is False
    assert evidence == []


def test_empty_owned_files_nonempty_breaking_returns_false():
    """Owned files empty, breaking files non-empty → (False, [])."""
    has_ev, evidence = validate_regression_ownership(
        feature_id="feat-boundary",
        owned_files=set(),
        breaking_files={"src/foo.py"},
    )
    assert has_ev is False
    assert evidence == []


def test_nonempty_owned_files_empty_breaking_returns_false():
    """Owned files non-empty, breaking files empty → (False, [])."""
    has_ev, evidence = validate_regression_ownership(
        feature_id="feat-boundary",
        owned_files={"src/foo.py"},
        breaking_files=set(),
    )
    assert has_ev is False
    assert evidence == []


def test_single_owned_file_matches_breaking_returns_true():
    """Minimum overlap: one file owned, same file in breaking → (True, evidence)."""
    has_ev, evidence = validate_regression_ownership(
        feature_id="feat-boundary",
        owned_files={"src/only.py"},
        breaking_files={"src/only.py"},
    )
    assert has_ev is True
    assert len(evidence) >= 1


def test_single_file_no_match_returns_false():
    """Minimum non-overlap: one file owned, different file in breaking → (False, [])."""
    has_ev, evidence = validate_regression_ownership(
        feature_id="feat-boundary",
        owned_files={"src/a.py"},
        breaking_files={"src/b.py"},
    )
    assert has_ev is False
    assert evidence == []


def test_transitive_deps_none_does_not_raise():
    """Passing None for transitive_deps is explicitly allowed and handled."""
    has_ev, evidence = validate_regression_ownership(
        feature_id="feat-boundary",
        owned_files={"src/foo.py"},
        breaking_files={"src/bar.py"},
        transitive_deps=None,
    )
    assert has_ev is False
    assert evidence == []


def test_transitive_deps_empty_dict_returns_false():
    """Empty transitive_deps dict with no direct overlap → (False, [])."""
    has_ev, evidence = validate_regression_ownership(
        feature_id="feat-boundary",
        owned_files={"src/foo.py"},
        breaking_files={"src/bar.py"},
        transitive_deps={},
    )
    assert has_ev is False
    assert evidence == []


def test_max_transitive_depth_zero_only_direct():
    """max_transitive_depth=0: no transitive lookup; only direct overlap counts."""
    has_ev, evidence = validate_regression_ownership(
        feature_id="feat-boundary",
        owned_files={"src/foo.py"},
        breaking_files={"src/bar.py"},
        transitive_deps={"src/foo.py": {"src/bar.py"}},
        max_transitive_depth=0,
    )
    assert has_ev is False
    assert evidence == []


def test_frozenset_accepted_as_owned_files():
    """frozenset is a valid owned_files input (subclass of frozenset)."""
    has_ev, evidence = validate_regression_ownership(
        feature_id="feat-boundary",
        owned_files=frozenset({"src/x.py"}),
        breaking_files={"src/x.py"},
    )
    assert has_ev is True


def test_frozenset_accepted_as_breaking_files():
    """frozenset is a valid breaking_files input."""
    has_ev, evidence = validate_regression_ownership(
        feature_id="feat-boundary",
        owned_files={"src/x.py"},
        breaking_files=frozenset({"src/x.py"}),
    )
    assert has_ev is True
