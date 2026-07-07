"""Boundary tests — empty / zero / minimum input returns a well-defined result.

Feature f3a62a46-d21b-4708-9331-79886d1411d2
"""

from __future__ import annotations

from bob.scoped_incremental_build import (
    incremental_build_targets,
    attribute_new_warnings_vs_baseline,
)


class TestIncrementalBuildTargetsBoundary:
    def test_empty_edited_tus_returns_empty_plan(self):
        plan = incremental_build_targets([], dependency_graph={})
        assert plan.targets == []
        assert plan.edited_translation_units == []
        assert plan.is_full_rebuild is False

    def test_empty_edited_tus_with_populated_graph_still_empty(self):
        plan = incremental_build_targets(
            [], dependency_graph={"src/a.cpp": ["libA.so"]}
        )
        assert plan.targets == []

    def test_omitted_dependency_graph_defaults_gracefully(self):
        plan = incremental_build_targets([])
        assert plan.targets == []


class TestAttributeNewWarningsBoundary:
    def test_empty_current_and_baseline(self):
        result = attribute_new_warnings_vs_baseline([], [], changed_files=[])
        assert result.new_warnings == []
        assert result.confidence_demoted is False

    def test_empty_current_with_baseline_warnings(self):
        result = attribute_new_warnings_vs_baseline(
            [], ["src/a.cpp:1:1: warning: w [-Wfoo]"], changed_files=["src/a.cpp"]
        )
        assert result.new_warnings == []
        assert result.confidence_demoted is False

    def test_empty_string_inputs(self):
        result = attribute_new_warnings_vs_baseline("", "", changed_files=[])
        assert result.new_warnings == []
        assert result.confidence_demoted is False
