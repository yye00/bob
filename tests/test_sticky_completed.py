"""Tests for bob3.sticky_completed.should_reset_completion_stamp.

Feature 69db3040 — Sticky-completed gate — re-evaluation cannot un-complete
persisted work.
"""

from __future__ import annotations

import json
import pathlib
import types

import pytest

from bob3.sticky_completed import should_reset_completion_stamp


def _make_feature(acceptance_criteria=None):
    """Create a minimal Feature-like object."""
    f = types.SimpleNamespace()
    f.id = "69db3040-ccb1-4315-a394-63c06d974d2b"
    f.acceptance_criteria = acceptance_criteria
    return f


class TestShouldResetCompletionStamp:
    """Core behavior of should_reset_completion_stamp."""

    def test_no_ac_paths_returns_false(self, tmp_path):
        """When no file-existence ACs exist, stamp should not be reset."""
        feature = _make_feature(acceptance_criteria=json.dumps([
            "integration: bob3.evaluator",
            "Function defined: bob3.sticky_completed.should_reset_completion_stamp",
        ]))
        result = should_reset_completion_stamp(feature, workspace=tmp_path)
        assert result is False

    def test_none_acceptance_criteria_returns_false(self, tmp_path):
        """None acceptance_criteria means no paths to check; returns False."""
        feature = _make_feature(acceptance_criteria=None)
        result = should_reset_completion_stamp(feature, workspace=tmp_path)
        assert result is False

    def test_empty_list_ac_returns_false(self, tmp_path):
        """Empty AC list means no file paths; returns False."""
        feature = _make_feature(acceptance_criteria=json.dumps([]))
        result = should_reset_completion_stamp(feature, workspace=tmp_path)
        assert result is False

    def test_mtime_modified_file_returns_true(self, tmp_path):
        """File modified after since_mtime threshold triggers stamp reset."""
        target = tmp_path / "src" / "mod.py"
        target.parent.mkdir(parents=True)
        target.write_text("# content\n")
        mtime_before = target.stat().st_mtime - 1.0  # threshold is 1 sec before

        feature = _make_feature(acceptance_criteria=json.dumps([
            "File exists: src/mod.py",
        ]))
        result = should_reset_completion_stamp(
            feature, workspace=tmp_path, since_mtime=mtime_before
        )
        assert result is True

    def test_mtime_unmodified_file_returns_false(self, tmp_path):
        """File not modified after since_mtime threshold — stamp stays."""
        target = tmp_path / "src" / "mod.py"
        target.parent.mkdir(parents=True)
        target.write_text("# content\n")
        mtime_after = target.stat().st_mtime + 1000.0  # threshold far in future

        feature = _make_feature(acceptance_criteria=json.dumps([
            "File exists: src/mod.py",
        ]))
        result = should_reset_completion_stamp(
            feature, workspace=tmp_path, since_mtime=mtime_after
        )
        assert result is False

    def test_missing_file_with_mtime_returns_false(self, tmp_path):
        """AC-named file doesn't exist — can't detect modification; returns False."""
        feature = _make_feature(acceptance_criteria=json.dumps([
            "File exists: src/nonexistent.py",
        ]))
        result = should_reset_completion_stamp(
            feature, workspace=tmp_path, since_mtime=0.0
        )
        assert result is False

    def test_pytest_ac_path_checked(self, tmp_path):
        """pytest: AC paths are also checked for modification."""
        target = tmp_path / "tests" / "test_mod.py"
        target.parent.mkdir(parents=True)
        target.write_text("# test\n")
        mtime_before = target.stat().st_mtime - 1.0

        feature = _make_feature(acceptance_criteria=json.dumps([
            "pytest: tests/test_mod.py",
        ]))
        result = should_reset_completion_stamp(
            feature, workspace=tmp_path, since_mtime=mtime_before
        )
        assert result is True

    def test_default_workspace_is_cwd(self):
        """When workspace is None, defaults to cwd() without raising."""
        feature = _make_feature(acceptance_criteria=json.dumps([]))
        # Should not raise; returns False because no AC paths
        result = should_reset_completion_stamp(feature)
        assert result is False

    def test_returns_bool(self, tmp_path):
        """Return value is always a bool."""
        feature = _make_feature(acceptance_criteria=None)
        result = should_reset_completion_stamp(feature, workspace=tmp_path)
        assert isinstance(result, bool)


class TestShouldResetCompletionStampErrors:
    """Error paths for should_reset_completion_stamp."""

    def test_none_feature_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="feature"):
            should_reset_completion_stamp(None, workspace=tmp_path)

    def test_feature_without_ac_attribute_raises_value_error(self, tmp_path):
        feature = types.SimpleNamespace(id="abc123")  # no acceptance_criteria attr
        with pytest.raises(ValueError, match="acceptance_criteria"):
            should_reset_completion_stamp(feature, workspace=tmp_path)


class TestEvaluatorIntegration:
    """Verify bob3.evaluator exposes should_reset_completion_stamp."""

    def test_evaluator_exports_function(self):
        from bob3 import evaluator
        assert hasattr(evaluator, "should_reset_completion_stamp")
        assert callable(evaluator.should_reset_completion_stamp)

    def test_evaluator_function_is_same_object(self):
        from bob3 import evaluator
        from bob3.sticky_completed import should_reset_completion_stamp as direct

        assert evaluator.should_reset_completion_stamp is direct
