"""Tests that critique_feature([]) returns empty findings list.

AC: pytest: tests/test_spec_critic_boundary_empty_feature_list.py
    asserts critique_feature([]) returns empty findings list (zero/empty edge)
"""

from __future__ import annotations

import pytest

from bob.spec_quality.spec_critic import critique_feature


class TestBoundaryEmptyFeatureList:
    def test_empty_ac_list_returns_empty_findings(self, tmp_path):
        """critique_feature([]) returns an empty list, not an error."""
        constitution = tmp_path / "spec_constitution.md"
        constitution.write_text('version: "1.0"\n\nNo principles yet.\n')

        result = critique_feature(
            feature_id="feat-empty",
            name="Empty Feature",
            description="A feature with no acceptance criteria.",
            acceptance_criteria=[],
            constitution_path=constitution,
        )

        assert result == []

    def test_empty_ac_list_returns_list_type(self, tmp_path):
        """Return value is specifically a list, not None or other type."""
        constitution = tmp_path / "spec_constitution.md"
        constitution.write_text('version: "1.0"\n\nConstitution content.\n')

        result = critique_feature(
            feature_id="feat-empty-2",
            name="Another Empty Feature",
            description="No ACs here.",
            acceptance_criteria=[],
            constitution_path=constitution,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_empty_ac_list_does_not_raise(self, tmp_path):
        """critique_feature([]) must not raise any exception."""
        constitution = tmp_path / "spec_constitution.md"
        constitution.write_text('version: "1.0"\n\nConstitution content.\n')

        # Should complete without raising
        critique_feature(
            feature_id="feat-no-crash",
            name="No ACs Feature",
            description="Should not crash with empty list.",
            acceptance_criteria=[],
            constitution_path=constitution,
        )

    def test_none_acceptance_criteria_edge_case(self, tmp_path):
        """Passing an empty list (not None) is the zero-AC edge case."""
        constitution = tmp_path / "spec_constitution.md"
        constitution.write_text('version: "1.0"\n\nConstitution content.\n')

        # Empty list is documented boundary; verify it's handled cleanly
        result = critique_feature(
            feature_id="feat-zero-ac",
            name="Zero AC Feature",
            description="Edge case: explicitly zero acceptance criteria.",
            acceptance_criteria=[],
            constitution_path=constitution,
        )

        assert result == [], f"Expected [], got {result}"
