"""Tests for ownership_evidenced_regression_detection_no_scapegoat.

Feature b0265f37-f7a5-44a0-a0b7-ca4876c4162f

Verifies:
- Features are only demoted when their own files appear in the breaking diff.
- Features with no file overlap are never scapegoated; unattributed event filed.
- Tests with no owner in the ownership map go to the unattributed bucket.
- Transitive dependency links are honoured (up to max_transitive_depth).
- Empty before/after yields an empty result.
- The main entry point function is importable and callable.
"""

from __future__ import annotations

import pytest

from bob3.ownership_evidenced_regression_detection_no_scapegoat import (
    UNATTRIBUTED_KEY,
    has_ownership_evidence,
    ownership_evidenced_regression_detection_no_scapegoat,
)


# ---------------------------------------------------------------------------
# Canonical AC test (required by feature spec)
# ---------------------------------------------------------------------------

def test_ownership_evidenced_regression_detection_no_scapegoat():
    """Main AC: features without ownership evidence are never demoted."""
    before = {
        "tests/test_alpha.py::test_one": True,
        "tests/test_beta.py::test_two": True,
        "tests/test_orphan.py::test_x": True,
    }
    after = {
        "tests/test_alpha.py::test_one": False,   # newly failing
        "tests/test_beta.py::test_two": True,      # still passing
        "tests/test_orphan.py::test_x": False,    # newly failing, no owner
    }
    test_to_feature_map = {
        "tests/test_alpha.py::test_one": "feat-alpha",
        "tests/test_beta.py::test_two": "feat-beta",
        # test_orphan has no entry → unattributed
    }
    ownership_map = {
        "feat-alpha": {"src/alpha.py"},
        "feat-beta": {"src/beta.py"},
    }
    # Only feat-alpha's file is in the breaking diff
    breaking_files = {"src/alpha.py", "src/shared_util.py"}

    demoted_calls: list[tuple] = []
    events: list[tuple] = []

    def update_fn(fid, status):
        demoted_calls.append((fid, status))

    def emit_fn(event_type, **kwargs):
        events.append((event_type, kwargs))

    result = ownership_evidenced_regression_detection_no_scapegoat(
        before_results=before,
        after_results=after,
        test_to_feature_map=test_to_feature_map,
        ownership_map=ownership_map,
        breaking_files=breaking_files,
        _update_feature_fn=update_fn,
        _emit_event_fn=emit_fn,
    )

    # feat-alpha: owned file "src/alpha.py" is in breaking_files → demoted
    assert "feat-alpha" in result["demoted"], "feat-alpha should be demoted (has evidence)"
    assert result["demoted"]["feat-alpha"]["tests"] == ["tests/test_alpha.py::test_one"]
    assert any("src/alpha.py" in e for e in result["demoted"]["feat-alpha"]["evidence"])
    assert ("feat-alpha", "regression") in demoted_calls

    # feat-beta: its test passes → not in demoted, not scapegoated
    assert "feat-beta" not in result["demoted"], "feat-beta's test still passes; must not be demoted"

    # orphan test: no owner → unattributed.no_owner
    assert "tests/test_orphan.py::test_x" in result["unattributed"]["no_owner"]

    # At least one regression_unattributed event for the orphan
    event_types = [e[0] for e in events]
    assert "regression_unattributed" in event_types


# ---------------------------------------------------------------------------
# has_ownership_evidence unit tests
# ---------------------------------------------------------------------------

def test_has_ownership_evidence_direct_overlap():
    exists, evidence = has_ownership_evidence(
        feature_id="feat-x",
        owned_files={"src/x.py", "src/y.py"},
        breaking_files={"src/x.py", "src/other.py"},
    )
    assert exists is True
    assert any("src/x.py" in e for e in evidence)


def test_has_ownership_evidence_no_overlap():
    exists, evidence = has_ownership_evidence(
        feature_id="feat-x",
        owned_files={"src/x.py"},
        breaking_files={"src/unrelated.py"},
    )
    assert exists is False
    assert evidence == []


def test_has_ownership_evidence_transitive_link():
    transitive_deps = {
        "src/x.py": {"src/shared.py"},
        "src/shared.py": {"src/deep.py"},
    }
    exists, evidence = has_ownership_evidence(
        feature_id="feat-x",
        owned_files={"src/x.py"},
        breaking_files={"src/shared.py"},
        transitive_deps=transitive_deps,
    )
    assert exists is True
    assert any("src/shared.py" in e for e in evidence)


def test_has_ownership_evidence_transitive_depth_limit():
    # depth-2 transitive but max_transitive_depth=1 — should NOT find link
    transitive_deps = {
        "src/x.py": {"src/level1.py"},
        "src/level1.py": {"src/level2.py"},
    }
    exists, _ = has_ownership_evidence(
        feature_id="feat-x",
        owned_files={"src/x.py"},
        breaking_files={"src/level2.py"},
        transitive_deps=transitive_deps,
        max_transitive_depth=1,
    )
    assert exists is False


def test_has_ownership_evidence_empty_owned_files():
    exists, evidence = has_ownership_evidence(
        feature_id="feat-x",
        owned_files=set(),
        breaking_files={"src/any.py"},
    )
    assert exists is False
    assert evidence == []


def test_has_ownership_evidence_empty_breaking_files():
    exists, evidence = has_ownership_evidence(
        feature_id="feat-x",
        owned_files={"src/x.py"},
        breaking_files=set(),
    )
    assert exists is False
    assert evidence == []


# ---------------------------------------------------------------------------
# ownership_evidenced_regression_detection integration tests
# ---------------------------------------------------------------------------

def test_no_newly_failing_tests_returns_empty():
    before = {"tests/test_a.py::test_1": True}
    after = {"tests/test_a.py::test_1": True}   # still passing

    result = ownership_evidenced_regression_detection_no_scapegoat(
        before_results=before,
        after_results=after,
        test_to_feature_map={"tests/test_a.py::test_1": "feat-a"},
        ownership_map={"feat-a": {"src/a.py"}},
        breaking_files={"src/a.py"},
    )

    assert result["demoted"] == {}
    assert result["unattributed"]["no_owner"] == []
    assert result["unattributed"]["no_evidence"] == {}


def test_no_scapegoat_when_owned_file_not_in_diff():
    """Feature with failing owned test but no file in diff → rejected."""
    before = {"tests/test_victim.py::test_it": True}
    after = {"tests/test_victim.py::test_it": False}

    demoted_calls: list = []
    events: list = []

    result = ownership_evidenced_regression_detection_no_scapegoat(
        before_results=before,
        after_results=after,
        test_to_feature_map={"tests/test_victim.py::test_it": "feat-victim"},
        ownership_map={"feat-victim": {"src/victim.py"}},
        breaking_files={"src/unrelated.py"},   # feat-victim's file NOT here
        _update_feature_fn=lambda fid, s: demoted_calls.append(fid),
        _emit_event_fn=lambda evt, **kw: events.append(evt),
    )

    assert "feat-victim" not in result["demoted"], "feat-victim must NOT be scapegoated"
    assert "feat-victim" in result["unattributed"]["no_evidence"]
    assert demoted_calls == [], "no DB update should have been called"
    assert "regression_unattributed" in events


def test_unattributed_when_test_has_no_owner():
    before = {"tests/test_ghost.py::test_g": True}
    after = {"tests/test_ghost.py::test_g": False}

    events: list = []

    result = ownership_evidenced_regression_detection_no_scapegoat(
        before_results=before,
        after_results=after,
        test_to_feature_map={},   # no owner registered
        ownership_map={},
        breaking_files={"src/anything.py"},
        _emit_event_fn=lambda evt, **kw: events.append(evt),
    )

    assert "tests/test_ghost.py::test_g" in result["unattributed"]["no_owner"]
    assert result["demoted"] == {}
    assert "regression_unattributed" in events


def test_multiple_features_only_evidenced_one_demoted():
    before = {
        "tests/test_a.py::test_a": True,
        "tests/test_b.py::test_b": True,
    }
    after = {
        "tests/test_a.py::test_a": False,
        "tests/test_b.py::test_b": False,
    }
    test_to_feature_map = {
        "tests/test_a.py::test_a": "feat-a",
        "tests/test_b.py::test_b": "feat-b",
    }
    ownership_map = {
        "feat-a": {"src/a.py"},
        "feat-b": {"src/b.py"},
    }
    breaking_files = {"src/a.py"}   # only feat-a's file is here

    demoted_calls: list = []
    result = ownership_evidenced_regression_detection_no_scapegoat(
        before_results=before,
        after_results=after,
        test_to_feature_map=test_to_feature_map,
        ownership_map=ownership_map,
        breaking_files=breaking_files,
        _update_feature_fn=lambda fid, s: demoted_calls.append(fid),
    )

    assert "feat-a" in result["demoted"]
    assert "feat-b" not in result["demoted"]
    assert "feat-b" in result["unattributed"]["no_evidence"]
    assert demoted_calls == ["feat-a"]


def test_transitive_evidence_causes_demotion():
    before = {"tests/test_c.py::test_c": True}
    after = {"tests/test_c.py::test_c": False}

    transitive_deps = {"src/c.py": {"src/shared_lib.py"}}
    breaking_files = {"src/shared_lib.py"}   # reachable from src/c.py

    demoted_calls: list = []
    result = ownership_evidenced_regression_detection_no_scapegoat(
        before_results=before,
        after_results=after,
        test_to_feature_map={"tests/test_c.py::test_c": "feat-c"},
        ownership_map={"feat-c": {"src/c.py"}},
        breaking_files=breaking_files,
        transitive_deps=transitive_deps,
        _update_feature_fn=lambda fid, s: demoted_calls.append(fid),
    )

    assert "feat-c" in result["demoted"]
    assert demoted_calls == ["feat-c"]


def test_test_previously_failing_not_counted_as_newly_failing():
    """If a test was already failing before, it is NOT a regression."""
    before = {"tests/test_d.py::test_d": False}   # already failing
    after = {"tests/test_d.py::test_d": False}    # still failing

    demoted_calls: list = []
    result = ownership_evidenced_regression_detection_no_scapegoat(
        before_results=before,
        after_results=after,
        test_to_feature_map={"tests/test_d.py::test_d": "feat-d"},
        ownership_map={"feat-d": {"src/d.py"}},
        breaking_files={"src/d.py"},
        _update_feature_fn=lambda fid, s: demoted_calls.append(fid),
    )

    assert result["demoted"] == {}
    assert demoted_calls == []
