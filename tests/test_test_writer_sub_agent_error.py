"""Error-path tests for test_writer_agent.generate_failing_tests.

Verifies that invalid inputs raise ValueError and the function does not
silently succeed.
"""

from __future__ import annotations

import pytest

from bob3.orchestrator.test_writer_agent import generate_failing_tests


class TestGenerateFailingTestsErrorPath:
    def test_empty_feature_id_raises_value_error(self, tmp_path):
        """An empty feature_id string must raise ValueError, not silently proceed."""
        with pytest.raises(ValueError, match="feature_id"):
            generate_failing_tests("", ["File exists: src/x.py"], workspace=tmp_path)

    def test_whitespace_only_feature_id_raises_value_error(self, tmp_path):
        """A whitespace-only feature_id must raise ValueError."""
        with pytest.raises(ValueError, match="feature_id"):
            generate_failing_tests("   ", ["File exists: src/x.py"], workspace=tmp_path)

    def test_non_list_acceptance_criteria_raises_value_error(self, tmp_path):
        """Passing a non-list for acceptance_criteria must raise ValueError."""
        with pytest.raises(ValueError, match="acceptance_criteria"):
            generate_failing_tests("feat-err", "not a list", workspace=tmp_path)  # type: ignore[arg-type]

    def test_none_acceptance_criteria_raises_value_error(self, tmp_path):
        """Passing None for acceptance_criteria must raise ValueError."""
        with pytest.raises(ValueError, match="acceptance_criteria"):
            generate_failing_tests("feat-err-none", None, workspace=tmp_path)  # type: ignore[arg-type]

    def test_dict_acceptance_criteria_raises_value_error(self, tmp_path):
        """Passing a dict for acceptance_criteria must raise ValueError."""
        with pytest.raises(ValueError, match="acceptance_criteria"):
            generate_failing_tests("feat-err-dict", {"ac": "val"}, workspace=tmp_path)  # type: ignore[arg-type]
