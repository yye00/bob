"""Tests for scoped incremental build with compiler-warning baseline attribution.

Feature f3a62a46-d21b-4708-9331-79886d1411d2

Covers:
    incremental_build_targets — resolve the minimal set of ninja targets that
    depend on the edited translation units (the C++ analog of scoping pytest to
    a feature's own subtree), plus spurious full-rebuild detection.

    attribute_new_warnings_vs_baseline — diff the compiler diagnostic stream
    against a bootstrap baseline so pre-existing brownfield warnings don't
    scapegoat the current feature; only NEW warnings on the changed files
    demote confidence.
"""

from __future__ import annotations

import pytest

from bob.scoped_incremental_build import (
    incremental_build_targets,
    attribute_new_warnings_vs_baseline,
)


# ---------------------------------------------------------------------------
# incremental_build_targets
# ---------------------------------------------------------------------------


class TestIncrementalBuildTargets:
    def test_importable(self):
        assert callable(incremental_build_targets)

    def test_only_targets_depending_on_edited_tus(self):
        graph = {
            "src/all_reduce.cpp": ["librccl_gfx90a.so", "librccl_gfx942.so"],
            "src/broadcast.cpp": ["librccl_gfx90a.so"],
            "src/unrelated.cpp": ["libother.so"],
        }
        plan = incremental_build_targets(
            ["src/all_reduce.cpp"], dependency_graph=graph
        )
        assert set(plan.targets) == {"librccl_gfx90a.so", "librccl_gfx942.so"}
        assert plan.edited_translation_units == ["src/all_reduce.cpp"]
        assert plan.is_full_rebuild is False

    def test_union_of_targets_across_multiple_edits(self):
        graph = {
            "src/a.cpp": ["libA.so"],
            "src/b.cpp": ["libB.so"],
        }
        plan = incremental_build_targets(
            ["src/a.cpp", "src/b.cpp"], dependency_graph=graph
        )
        assert set(plan.targets) == {"libA.so", "libB.so"}

    def test_targets_are_deduplicated_and_sorted(self):
        graph = {
            "src/a.cpp": ["libZ.so", "libA.so"],
            "src/b.cpp": ["libA.so"],
        }
        plan = incremental_build_targets(
            ["src/a.cpp", "src/b.cpp"], dependency_graph=graph
        )
        # dedup: libA appears twice, sorted deterministically
        assert plan.targets == ["libA.so", "libZ.so"]

    def test_edited_tu_absent_from_graph_falls_back_to_tu_itself(self):
        # An edited file with no known dependents still gets scheduled so the
        # build is never a silent no-op.
        plan = incremental_build_targets(["src/new_file.cpp"], dependency_graph={})
        assert "src/new_file.cpp" in plan.targets

    def test_ninja_explain_detects_spurious_full_rebuild(self):
        graph = {"src/a.cpp": ["libA.so"]}
        explain = (
            "ninja explain: output libB.so of phony edge with no inputs "
            "doesn't exist\n"
            "ninja explain: libEverything.so is dirty\n"
        ) * 200
        plan = incremental_build_targets(
            ["src/a.cpp"],
            dependency_graph=graph,
            ninja_explain_output=explain,
        )
        assert plan.spurious_rebuild_warning is not None
        assert "rebuild" in plan.spurious_rebuild_warning.lower()

    def test_clean_ninja_explain_no_spurious_warning(self):
        graph = {"src/a.cpp": ["libA.so"]}
        plan = incremental_build_targets(
            ["src/a.cpp"],
            dependency_graph=graph,
            ninja_explain_output="ninja explain: libA.so is dirty\n",
        )
        assert plan.spurious_rebuild_warning is None


# ---------------------------------------------------------------------------
# attribute_new_warnings_vs_baseline
# ---------------------------------------------------------------------------


class TestAttributeNewWarnings:
    def test_importable(self):
        assert callable(attribute_new_warnings_vs_baseline)

    def test_new_warning_on_changed_file_demotes_confidence(self):
        baseline = [
            "src/all_reduce.cpp:10:5: warning: unused variable 'x' [-Wunused-variable]",
        ]
        current = [
            "src/all_reduce.cpp:10:5: warning: unused variable 'x' [-Wunused-variable]",
            "src/all_reduce.cpp:42:9: warning: 'y' may be used uninitialized [-Wuninitialized]",
        ]
        result = attribute_new_warnings_vs_baseline(
            current, baseline, changed_files=["src/all_reduce.cpp"]
        )
        assert result.confidence_demoted is True
        assert len(result.new_warnings) == 1
        assert "uninitialized" in result.new_warnings[0]

    def test_preexisting_brownfield_warning_does_not_scapegoat(self):
        # A warning present at baseline must never be counted against the feature.
        baseline = [
            "src/legacy.cpp:5:1: warning: old brownfield warning [-Wsign-compare]",
        ]
        current = list(baseline)
        result = attribute_new_warnings_vs_baseline(
            current, baseline, changed_files=["src/legacy.cpp"]
        )
        assert result.new_warnings == []
        assert result.confidence_demoted is False

    def test_new_warning_on_unchanged_file_is_not_attributed(self):
        baseline: list[str] = []
        current = [
            "src/other_untouched.cpp:1:1: warning: something [-Wfoo]",
        ]
        result = attribute_new_warnings_vs_baseline(
            current, baseline, changed_files=["src/all_reduce.cpp"]
        )
        # New warning is on a file the feature did not touch → not its fault.
        assert result.new_warnings == []
        assert result.confidence_demoted is False

    def test_accepts_raw_compiler_output_strings(self):
        baseline = ""
        current = "src/a.cpp:3:3: warning: uh oh [-Wall]\n"
        result = attribute_new_warnings_vs_baseline(
            current, baseline, changed_files=["src/a.cpp"]
        )
        assert len(result.new_warnings) == 1
        assert result.confidence_demoted is True

    def test_no_changed_files_filter_considers_all_new_warnings(self):
        baseline: list[str] = []
        current = ["src/a.cpp:1:1: warning: w [-Wfoo]"]
        result = attribute_new_warnings_vs_baseline(current, baseline)
        assert len(result.new_warnings) == 1
