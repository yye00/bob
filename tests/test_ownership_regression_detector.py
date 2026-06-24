"""Tests for bob.ownership_regression_detector.

Feature 7b27b498-5cbb-4d96-be2f-2f612894adbc
Ownership-evidenced regression detection (no scapegoat without proof)

Verifies that:
1. verify_causal_link correctly identifies causal evidence (direct and transitive).
2. detect_regression_with_evidence only demotes features with a confirmed causal
   link; unattributed tests are filed as regression_unattributed events, never
   scapegoated onto unrelated features.
"""

from __future__ import annotations

import pytest

from bob.ownership_regression_detector import (
    detect_regression_with_evidence,
    verify_causal_link,
)


# ---------------------------------------------------------------------------
# verify_causal_link — happy-path tests
# ---------------------------------------------------------------------------

class TestVerifyCausalLinkHappyPath:
    def test_direct_overlap_returns_true_with_evidence(self):
        """A file owned by the feature that appears in breaking_files → True."""
        has_ev, evidence = verify_causal_link(
            feature_id="feat-a",
            owned_files={"src/foo.py", "src/bar.py"},
            breaking_files={"src/foo.py", "src/baz.py"},
        )
        assert has_ev is True
        assert len(evidence) >= 1
        assert any("src/foo.py" in e for e in evidence)

    def test_no_overlap_returns_false_empty_evidence(self):
        """No owned file in breaking_files → (False, [])."""
        has_ev, evidence = verify_causal_link(
            feature_id="feat-a",
            owned_files={"src/foo.py"},
            breaking_files={"src/bar.py"},
        )
        assert has_ev is False
        assert evidence == []

    def test_transitive_overlap_triggers_evidence(self):
        """Transitive dependency in breaking_files → (True, evidence)."""
        has_ev, evidence = verify_causal_link(
            feature_id="feat-a",
            owned_files={"src/foo.py"},
            breaking_files={"src/baz.py"},
            transitive_deps={"src/foo.py": {"src/bar.py"}, "src/bar.py": {"src/baz.py"}},
            max_transitive_depth=2,
        )
        assert has_ev is True
        assert len(evidence) >= 1

    def test_empty_owned_files_returns_false(self):
        """Empty owned_files → (False, []) without error."""
        has_ev, evidence = verify_causal_link(
            feature_id="feat-a",
            owned_files=set(),
            breaking_files={"src/foo.py"},
        )
        assert has_ev is False
        assert evidence == []

    def test_empty_breaking_files_returns_false(self):
        """Empty breaking_files → (False, []) without error."""
        has_ev, evidence = verify_causal_link(
            feature_id="feat-a",
            owned_files={"src/foo.py"},
            breaking_files=set(),
        )
        assert has_ev is False
        assert evidence == []

    def test_frozenset_inputs_accepted(self):
        """frozenset inputs for owned_files and breaking_files are valid."""
        has_ev, evidence = verify_causal_link(
            feature_id="feat-a",
            owned_files=frozenset({"src/foo.py"}),
            breaking_files=frozenset({"src/foo.py"}),
        )
        assert has_ev is True

    def test_transitive_depth_zero_ignores_deps(self):
        """max_transitive_depth=0: only direct overlap matters."""
        has_ev, evidence = verify_causal_link(
            feature_id="feat-a",
            owned_files={"src/foo.py"},
            breaking_files={"src/bar.py"},
            transitive_deps={"src/foo.py": {"src/bar.py"}},
            max_transitive_depth=0,
        )
        assert has_ev is False

    def test_none_transitive_deps_does_not_raise(self):
        """transitive_deps=None is valid and degrades gracefully."""
        has_ev, evidence = verify_causal_link(
            feature_id="feat-a",
            owned_files={"src/foo.py"},
            breaking_files={"src/bar.py"},
            transitive_deps=None,
        )
        assert has_ev is False
        assert evidence == []


# ---------------------------------------------------------------------------
# verify_causal_link — error-path tests
# ---------------------------------------------------------------------------

class TestVerifyCausalLinkErrorPath:
    def test_none_feature_id_raises_valueerror(self):
        with pytest.raises(ValueError):
            verify_causal_link(
                feature_id=None,
                owned_files={"src/foo.py"},
                breaking_files={"src/foo.py"},
            )

    def test_empty_feature_id_raises_valueerror(self):
        with pytest.raises(ValueError, match="feature_id"):
            verify_causal_link(
                feature_id="",
                owned_files={"src/foo.py"},
                breaking_files={"src/foo.py"},
            )

    def test_whitespace_feature_id_raises_valueerror(self):
        with pytest.raises(ValueError, match="feature_id"):
            verify_causal_link(
                feature_id="   ",
                owned_files={"src/foo.py"},
                breaking_files={"src/foo.py"},
            )

    def test_list_owned_files_raises_valueerror(self):
        with pytest.raises(ValueError, match="owned_files"):
            verify_causal_link(
                feature_id="feat-a",
                owned_files=["src/foo.py"],
                breaking_files={"src/foo.py"},
            )

    def test_list_breaking_files_raises_valueerror(self):
        with pytest.raises(ValueError, match="breaking_files"):
            verify_causal_link(
                feature_id="feat-a",
                owned_files={"src/foo.py"},
                breaking_files=["src/foo.py"],
            )


# ---------------------------------------------------------------------------
# detect_regression_with_evidence — core behavior
# ---------------------------------------------------------------------------

class TestDetectRegressionWithEvidence:
    def _make_update_fn(self):
        demoted = []
        def fn(fid, status):
            demoted.append((fid, status))
        return fn, demoted

    def _make_emit_fn(self):
        events = []
        def fn(event_type, **kwargs):
            events.append((event_type, kwargs))
        return fn, events

    def test_no_newly_failing_tests_returns_empty(self):
        """When all tests still pass, nothing is demoted."""
        result = detect_regression_with_evidence(
            before_results={"tests/test_foo.py::test_a": True},
            after_results={"tests/test_foo.py::test_a": True},
            test_to_feature_map={"tests/test_foo.py::test_a": "feat-a"},
            ownership_map={"feat-a": {"src/foo.py"}},
            breaking_files={"src/foo.py"},
        )
        assert result["demoted"] == {}
        assert result["unattributed"]["no_owner"] == []
        assert result["unattributed"]["no_evidence"] == {}

    def test_newly_failing_test_with_causal_link_demotes_feature(self):
        """A newly-failing owned test with causal evidence → feature demoted."""
        update_fn, demoted = self._make_update_fn()
        emit_fn, events = self._make_emit_fn()

        result = detect_regression_with_evidence(
            before_results={"tests/test_foo.py::test_a": True},
            after_results={"tests/test_foo.py::test_a": False},
            test_to_feature_map={"tests/test_foo.py::test_a": "feat-a"},
            ownership_map={"feat-a": {"src/foo.py"}},
            breaking_files={"src/foo.py"},
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        assert "feat-a" in result["demoted"]
        assert "tests/test_foo.py::test_a" in result["demoted"]["feat-a"]["tests"]
        assert len(result["demoted"]["feat-a"]["evidence"]) >= 1
        assert ("feat-a", "regression") in demoted

    def test_newly_failing_test_without_causal_link_not_demoted(self):
        """A newly-failing owned test WITHOUT causal evidence → filed as unattributed."""
        update_fn, demoted = self._make_update_fn()
        emit_fn, events = self._make_emit_fn()

        result = detect_regression_with_evidence(
            before_results={"tests/test_foo.py::test_a": True},
            after_results={"tests/test_foo.py::test_a": False},
            test_to_feature_map={"tests/test_foo.py::test_a": "feat-a"},
            ownership_map={"feat-a": {"src/foo.py"}},
            breaking_files={"src/completely_unrelated.py"},
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        assert result["demoted"] == {}
        assert "feat-a" in result["unattributed"]["no_evidence"]
        assert demoted == []
        regression_unattributed_events = [e for e in events if e[0] == "regression_unattributed"]
        assert len(regression_unattributed_events) >= 1

    def test_unowned_test_goes_to_no_owner_not_scapegoated(self):
        """A failing test with no owner is filed as unattributed, never blamed on other features."""
        update_fn, demoted = self._make_update_fn()
        emit_fn, events = self._make_emit_fn()

        result = detect_regression_with_evidence(
            before_results={"tests/test_orphan.py::test_x": True},
            after_results={"tests/test_orphan.py::test_x": False},
            test_to_feature_map={},
            ownership_map={"feat-a": {"src/foo.py"}},
            breaking_files={"src/foo.py"},
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        assert result["demoted"] == {}
        assert "tests/test_orphan.py::test_x" in result["unattributed"]["no_owner"]
        assert demoted == []

    def test_multiple_features_only_evidenced_one_demoted(self):
        """Multiple candidate features: only the one with causal evidence is demoted."""
        update_fn, demoted = self._make_update_fn()

        result = detect_regression_with_evidence(
            before_results={
                "tests/test_a.py::test_1": True,
                "tests/test_b.py::test_2": True,
            },
            after_results={
                "tests/test_a.py::test_1": False,
                "tests/test_b.py::test_2": False,
            },
            test_to_feature_map={
                "tests/test_a.py::test_1": "feat-a",
                "tests/test_b.py::test_2": "feat-b",
            },
            ownership_map={
                "feat-a": {"src/a.py"},   # touches breaking_files
                "feat-b": {"src/b.py"},   # does NOT touch breaking_files
            },
            breaking_files={"src/a.py"},
            _update_feature_fn=update_fn,
        )

        assert "feat-a" in result["demoted"]
        assert "feat-b" not in result["demoted"]
        assert "feat-b" in result["unattributed"]["no_evidence"]
        assert ("feat-a", "regression") in demoted
        assert ("feat-b", "regression") not in demoted

    def test_empty_inputs_return_empty_result(self):
        """Empty before/after results → empty result without error."""
        result = detect_regression_with_evidence(
            before_results={},
            after_results={},
            test_to_feature_map={},
            ownership_map={},
            breaking_files=set(),
        )
        assert result["demoted"] == {}
        assert result["unattributed"]["no_owner"] == []
        assert result["unattributed"]["no_evidence"] == {}

    def test_previously_failing_test_not_counted_as_newly_failing(self):
        """A test that was already failing before is not counted as a new regression."""
        update_fn, demoted = self._make_update_fn()

        result = detect_regression_with_evidence(
            before_results={"tests/test_a.py::test_1": False},  # was already failing
            after_results={"tests/test_a.py::test_1": False},
            test_to_feature_map={"tests/test_a.py::test_1": "feat-a"},
            ownership_map={"feat-a": {"src/a.py"}},
            breaking_files={"src/a.py"},
            _update_feature_fn=update_fn,
        )

        assert result["demoted"] == {}
        assert demoted == []

    def test_transitive_dep_provides_causal_link(self):
        """Causal link via transitive dependency → feature demoted."""
        update_fn, demoted = self._make_update_fn()

        result = detect_regression_with_evidence(
            before_results={"tests/test_a.py::test_1": True},
            after_results={"tests/test_a.py::test_1": False},
            test_to_feature_map={"tests/test_a.py::test_1": "feat-a"},
            ownership_map={"feat-a": {"src/a.py"}},
            breaking_files={"src/dep.py"},
            transitive_deps={"src/a.py": {"src/dep.py"}},
            _update_feature_fn=update_fn,
        )

        assert "feat-a" in result["demoted"]
        assert ("feat-a", "regression") in demoted


# ---------------------------------------------------------------------------
# detect_regression_with_evidence — error-path tests
# ---------------------------------------------------------------------------

class TestDetectRegressionErrorPath:
    def test_non_dict_before_results_raises_typeerror(self):
        with pytest.raises(TypeError, match="before_results"):
            detect_regression_with_evidence(
                before_results=[],
                after_results={},
                test_to_feature_map={},
                ownership_map={},
                breaking_files=set(),
            )

    def test_non_dict_after_results_raises_typeerror(self):
        with pytest.raises(TypeError, match="after_results"):
            detect_regression_with_evidence(
                before_results={},
                after_results=[],
                test_to_feature_map={},
                ownership_map={},
                breaking_files=set(),
            )

    def test_non_set_breaking_files_raises_typeerror(self):
        with pytest.raises(TypeError, match="breaking_files"):
            detect_regression_with_evidence(
                before_results={},
                after_results={},
                test_to_feature_map={},
                ownership_map={},
                breaking_files=["src/foo.py"],
            )
