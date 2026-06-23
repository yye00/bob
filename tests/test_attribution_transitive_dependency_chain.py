"""Test: transitive dependency attribution — if A imports B's module and B was touched, attribute to B.

Feature aaa5a7f7-74e2-4edc-b61c-ac822dfced4f

Depth limit: 3 hops maximum.
"""

from __future__ import annotations

import pytest


def _make_commit(commit_id: str, files_touched: list[str]):
    return {"commit_id": commit_id, "files_touched": files_touched}


class TestTransitiveAttributionChain:
    """attribute_breakage resolves transitive imports up to depth 3."""

    def test_importable(self):
        from bob3.orchestrator.regression_attribution import attribute_breakage
        assert callable(attribute_breakage)

    def test_direct_file_overlap_attributes_to_touched_feature(self):
        """A is broken, B was touched. If A imports B's file, attribute to B."""
        from bob3.orchestrator.regression_attribution import attribute_breakage
        # B owns src/b_module.py (the touched file)
        # A owns src/a_module.py (not touched, but imports B's file)
        ownership_map = {
            "feat-A": {"src/a_module.py"},
            "feat-B": {"src/b_module.py"},
        }
        recent_commits = [_make_commit("c1", ["src/b_module.py"])]

        # Transitive dependency map: a_module.py imports b_module.py
        transitive_deps = {"src/a_module.py": {"src/b_module.py"}}

        result = attribute_breakage(
            failing_test_id="tests/test_a.py::test_something",
            recent_commits=recent_commits,
            ownership_map=ownership_map,
            transitive_deps=transitive_deps,
        )
        # Should attribute to B since B was touched and A depends on B
        assert result["attributed_feature"] == "feat-B"
        assert result["confidence"] > 0.0

    def test_no_transitive_dep_keeps_no_attribution(self):
        """Without a transitive dependency, unrelated features stay safe."""
        from bob3.orchestrator.regression_attribution import attribute_breakage
        ownership_map = {
            "feat-A": {"src/a_module.py"},
            "feat-B": {"src/b_module.py"},
        }
        recent_commits = [_make_commit("c1", ["src/b_module.py"])]

        # No transitive deps
        result = attribute_breakage(
            failing_test_id="tests/test_a.py::test_something",
            recent_commits=recent_commits,
            ownership_map=ownership_map,
            transitive_deps={},  # no dependencies
        )
        # A does not depend on B and A was not touched — no attribution
        assert result["attributed_feature"] is None

    def test_depth_3_limit_is_respected(self):
        """Dependency chains deeper than 3 hops are not followed."""
        from bob3.orchestrator.regression_attribution import attribute_breakage
        # Chain: A → B → C → D → E (depth 4 from A to E)
        # Only E was touched
        ownership_map = {
            "feat-A": {"src/a.py"},
            "feat-B": {"src/b.py"},
            "feat-C": {"src/c.py"},
            "feat-D": {"src/d.py"},
            "feat-E": {"src/e.py"},
        }
        recent_commits = [_make_commit("c1", ["src/e.py"])]
        # Chain depth 4 from a.py to e.py
        transitive_deps = {
            "src/a.py": {"src/b.py"},
            "src/b.py": {"src/c.py"},
            "src/c.py": {"src/d.py"},
            "src/d.py": {"src/e.py"},
        }

        result = attribute_breakage(
            failing_test_id="tests/test_a.py::test_something",
            recent_commits=recent_commits,
            ownership_map=ownership_map,
            transitive_deps=transitive_deps,
        )
        # Depth 4 chain exceeds max depth 3 — should NOT attribute
        assert result["attributed_feature"] is None

    def test_depth_3_chain_is_followed(self):
        """A → B → C → D at depth 3 should be followed if D was touched."""
        from bob3.orchestrator.regression_attribution import attribute_breakage
        # A depends on B (depth 1), B depends on C (depth 2), C depends on D (depth 3)
        ownership_map = {
            "feat-A": {"src/a.py"},
            "feat-B": {"src/b.py"},
            "feat-C": {"src/c.py"},
            "feat-D": {"src/d.py"},
        }
        recent_commits = [_make_commit("c1", ["src/d.py"])]
        transitive_deps = {
            "src/a.py": {"src/b.py"},
            "src/b.py": {"src/c.py"},
            "src/c.py": {"src/d.py"},
        }

        result = attribute_breakage(
            failing_test_id="tests/test_a.py::test_something",
            recent_commits=recent_commits,
            ownership_map=ownership_map,
            transitive_deps=transitive_deps,
        )
        # Depth 3 from a.py to d.py — should attribute to feat-D
        assert result["attributed_feature"] == "feat-D"

    def test_transitive_deps_optional_parameter(self):
        """attribute_breakage works without transitive_deps (defaults to empty)."""
        from bob3.orchestrator.regression_attribution import attribute_breakage
        ownership_map = {"feat-A": {"src/foo.py"}}
        recent_commits = [_make_commit("c1", ["src/foo.py"])]

        # No transitive_deps parameter — should still attribute via direct overlap
        result = attribute_breakage(
            failing_test_id="tests/test_a.py::test_one",
            recent_commits=recent_commits,
            ownership_map=ownership_map,
        )
        assert result["attributed_feature"] == "feat-A"
