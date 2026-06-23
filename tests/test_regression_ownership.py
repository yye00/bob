"""Tests for bob3.regression.check_regression_ownership and find_touching_commits.

Feature 270d01f1-1208-4968-adb3-f0af1d7c1a40 — Ownership-evidenced regression detection.

Verifies that:
- check_regression_ownership returns (True, evidence) only when a causal link exists.
- check_regression_ownership rejects invalid inputs with ValueError.
- find_touching_commits returns only commits that touch owned files.
- find_touching_commits rejects invalid inputs with ValueError.
- Neither function scapegoats a feature that has no causal link.
"""

from __future__ import annotations

import pytest

from bob3.regression import check_regression_ownership, find_touching_commits


# ---------------------------------------------------------------------------
# check_regression_ownership — happy-path tests
# ---------------------------------------------------------------------------


def test_check_regression_ownership_direct_match():
    """A commit touching an owned file establishes a causal link."""
    has_ev, evidence = check_regression_ownership(
        feature_id="feat-A",
        owned_files={"src/feature_a.py"},
        recent_commits=[
            {"commit_id": "abc123", "files_touched": ["src/feature_a.py", "src/other.py"]},
        ],
    )
    assert has_ev is True
    assert len(evidence) >= 1
    assert any("src/feature_a.py" in e for e in evidence)


def test_check_regression_ownership_no_overlap_returns_false():
    """No shared files between owned set and breaking commits → no causal link."""
    has_ev, evidence = check_regression_ownership(
        feature_id="feat-B",
        owned_files={"src/feature_b.py"},
        recent_commits=[
            {"commit_id": "def456", "files_touched": ["src/unrelated.py"]},
        ],
    )
    assert has_ev is False
    assert evidence == []


def test_check_regression_ownership_multiple_commits_union():
    """Breaking files are derived from the union of all commits."""
    has_ev, evidence = check_regression_ownership(
        feature_id="feat-C",
        owned_files={"src/feature_c.py"},
        recent_commits=[
            {"commit_id": "c001", "files_touched": ["src/a.py"]},
            {"commit_id": "c002", "files_touched": ["src/feature_c.py"]},
        ],
    )
    assert has_ev is True


def test_check_regression_ownership_empty_commits_returns_false():
    """No commits → no breaking files → no causal link."""
    has_ev, evidence = check_regression_ownership(
        feature_id="feat-D",
        owned_files={"src/feature_d.py"},
        recent_commits=[],
    )
    assert has_ev is False
    assert evidence == []


def test_check_regression_ownership_transitive_link():
    """A transitive import link establishes a causal link."""
    transitive_deps = {
        "src/feature_e.py": {"src/lib.py"},
    }
    has_ev, evidence = check_regression_ownership(
        feature_id="feat-E",
        owned_files={"src/feature_e.py"},
        recent_commits=[
            {"commit_id": "e001", "files_touched": ["src/lib.py"]},
        ],
        transitive_deps=transitive_deps,
    )
    assert has_ev is True


def test_check_regression_ownership_no_scapegoat_without_evidence():
    """An unrelated feature is NOT blamed just because tests fail."""
    has_ev, evidence = check_regression_ownership(
        feature_id="innocent-feature",
        owned_files={"src/innocent.py"},
        recent_commits=[
            {"commit_id": "f001", "files_touched": ["src/culprit.py"]},
        ],
    )
    assert has_ev is False
    assert evidence == []


# ---------------------------------------------------------------------------
# check_regression_ownership — error-path tests
# ---------------------------------------------------------------------------


def test_check_regression_ownership_empty_feature_id_raises():
    with pytest.raises(ValueError, match="feature_id"):
        check_regression_ownership(
            feature_id="",
            owned_files={"src/foo.py"},
            recent_commits=[],
        )


def test_check_regression_ownership_none_feature_id_raises():
    with pytest.raises(ValueError):
        check_regression_ownership(
            feature_id=None,
            owned_files={"src/foo.py"},
            recent_commits=[],
        )


def test_check_regression_ownership_whitespace_feature_id_raises():
    with pytest.raises(ValueError, match="feature_id"):
        check_regression_ownership(
            feature_id="   ",
            owned_files={"src/foo.py"},
            recent_commits=[],
        )


def test_check_regression_ownership_list_owned_files_raises():
    with pytest.raises(ValueError, match="owned_files"):
        check_regression_ownership(
            feature_id="feat-err",
            owned_files=["src/foo.py"],
            recent_commits=[],
        )


def test_check_regression_ownership_dict_owned_files_raises():
    with pytest.raises(ValueError, match="owned_files"):
        check_regression_ownership(
            feature_id="feat-err",
            owned_files={"src/foo.py": True},
            recent_commits=[],
        )


def test_check_regression_ownership_tuple_commits_raises():
    with pytest.raises(ValueError, match="recent_commits"):
        check_regression_ownership(
            feature_id="feat-err",
            owned_files={"src/foo.py"},
            recent_commits=({"commit_id": "x", "files_touched": []},),
        )


# ---------------------------------------------------------------------------
# find_touching_commits — happy-path tests
# ---------------------------------------------------------------------------


def test_find_touching_commits_returns_matching_commits():
    """Commits touching owned files are returned."""
    commits = [
        {"commit_id": "a1", "files_touched": ["src/feat_a.py"]},
        {"commit_id": "b2", "files_touched": ["src/unrelated.py"]},
    ]
    result = find_touching_commits(
        feature_id="feat-A",
        owned_files={"src/feat_a.py"},
        commits=commits,
    )
    assert len(result) == 1
    assert result[0]["commit_id"] == "a1"


def test_find_touching_commits_empty_owned_returns_empty():
    """No owned files → no touching commits."""
    commits = [
        {"commit_id": "a1", "files_touched": ["src/anything.py"]},
    ]
    result = find_touching_commits(
        feature_id="feat-empty",
        owned_files=set(),
        commits=commits,
    )
    assert result == []


def test_find_touching_commits_no_overlap_returns_empty():
    """Commits don't touch owned files → empty result."""
    commits = [
        {"commit_id": "x1", "files_touched": ["src/other.py"]},
    ]
    result = find_touching_commits(
        feature_id="feat-B",
        owned_files={"src/feat_b.py"},
        commits=commits,
    )
    assert result == []


def test_find_touching_commits_empty_commits_returns_empty():
    """No commits → empty result."""
    result = find_touching_commits(
        feature_id="feat-C",
        owned_files={"src/feat_c.py"},
        commits=[],
    )
    assert result == []


def test_find_touching_commits_multiple_matching():
    """Multiple touching commits are all returned."""
    commits = [
        {"commit_id": "m1", "files_touched": ["src/feat_m.py"]},
        {"commit_id": "m2", "files_touched": ["src/feat_m.py", "src/other.py"]},
        {"commit_id": "m3", "files_touched": ["src/completely_unrelated.py"]},
    ]
    result = find_touching_commits(
        feature_id="feat-M",
        owned_files={"src/feat_m.py"},
        commits=commits,
    )
    assert len(result) == 2
    ids = {c["commit_id"] for c in result}
    assert ids == {"m1", "m2"}


def test_find_touching_commits_transitive_link():
    """Transitive import links are followed when transitive_deps is provided."""
    transitive_deps = {
        "src/feat_t.py": {"src/lib_t.py"},
    }
    commits = [
        {"commit_id": "t1", "files_touched": ["src/lib_t.py"]},
        {"commit_id": "t2", "files_touched": ["src/unrelated.py"]},
    ]
    result = find_touching_commits(
        feature_id="feat-T",
        owned_files={"src/feat_t.py"},
        commits=commits,
        transitive_deps=transitive_deps,
    )
    assert len(result) == 1
    assert result[0]["commit_id"] == "t1"


def test_find_touching_commits_skips_commits_with_no_files():
    """Commits with empty files_touched are skipped without error."""
    commits = [
        {"commit_id": "empty1", "files_touched": []},
        {"commit_id": "real1", "files_touched": ["src/feat_r.py"]},
    ]
    result = find_touching_commits(
        feature_id="feat-R",
        owned_files={"src/feat_r.py"},
        commits=commits,
    )
    assert len(result) == 1
    assert result[0]["commit_id"] == "real1"


# ---------------------------------------------------------------------------
# find_touching_commits — error-path tests
# ---------------------------------------------------------------------------


def test_find_touching_commits_empty_feature_id_raises():
    with pytest.raises(ValueError, match="feature_id"):
        find_touching_commits(
            feature_id="",
            owned_files={"src/foo.py"},
            commits=[],
        )


def test_find_touching_commits_none_feature_id_raises():
    with pytest.raises(ValueError):
        find_touching_commits(
            feature_id=None,
            owned_files={"src/foo.py"},
            commits=[],
        )


def test_find_touching_commits_list_owned_files_raises():
    with pytest.raises(ValueError, match="owned_files"):
        find_touching_commits(
            feature_id="feat-err",
            owned_files=["src/foo.py"],
            commits=[],
        )


def test_find_touching_commits_tuple_commits_raises():
    with pytest.raises(ValueError, match="commits"):
        find_touching_commits(
            feature_id="feat-err",
            owned_files={"src/foo.py"},
            commits=({"commit_id": "x", "files_touched": []},),
        )


# ---------------------------------------------------------------------------
# Integration: orchestrator re-exports both functions
# ---------------------------------------------------------------------------


def test_orchestrator_exports_check_regression_ownership():
    """bob3.orchestrator must re-export check_regression_ownership."""
    from bob3.orchestrator import check_regression_ownership as fn  # noqa: F401
    assert callable(fn)


def test_orchestrator_exports_find_touching_commits():
    """bob3.orchestrator must re-export find_touching_commits."""
    from bob3.orchestrator import find_touching_commits as fn  # noqa: F401
    assert callable(fn)
