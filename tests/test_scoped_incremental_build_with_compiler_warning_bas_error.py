"""Error tests — invalid input raises ValueError, no silent success.

Feature f3a62a46-d21b-4708-9331-79886d1411d2
"""

from __future__ import annotations

import pytest

from bob.scoped_incremental_build import (
    incremental_build_targets,
    attribute_new_warnings_vs_baseline,
)


class TestIncrementalBuildTargetsErrors:
    def test_none_edited_tus_raises(self):
        with pytest.raises(ValueError):
            incremental_build_targets(None, dependency_graph={})

    def test_edited_tus_wrong_type_raises(self):
        with pytest.raises(ValueError):
            incremental_build_targets("src/a.cpp", dependency_graph={})

    def test_non_string_tu_entry_raises(self):
        with pytest.raises(ValueError):
            incremental_build_targets([123], dependency_graph={})

    def test_dependency_graph_wrong_type_raises(self):
        with pytest.raises(ValueError):
            incremental_build_targets(["src/a.cpp"], dependency_graph=["not", "a", "dict"])


class TestAttributeNewWarningsErrors:
    def test_none_current_raises(self):
        with pytest.raises(ValueError):
            attribute_new_warnings_vs_baseline(None, [])

    def test_none_baseline_raises(self):
        with pytest.raises(ValueError):
            attribute_new_warnings_vs_baseline([], None)

    def test_current_wrong_type_raises(self):
        with pytest.raises(ValueError):
            attribute_new_warnings_vs_baseline(123, [])

    def test_changed_files_wrong_type_raises(self):
        with pytest.raises(ValueError):
            attribute_new_warnings_vs_baseline([], [], changed_files="src/a.cpp")
