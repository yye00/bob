"""Tests that critique_feature raises ConstitutionMissingError when spec_constitution.md absent.

AC: pytest: tests/test_spec_critic_handles_missing_constitution.py
    asserts critique_feature raises ConstitutionMissingError when
    spec_constitution.md absent (missing-file error path)
"""

from __future__ import annotations

import pytest

from bob.spec_quality.spec_critic import (
    ConstitutionMissingError,
    critique_feature,
    handle_empty_constitution,
)


class TestMissingConstitution:
    def test_critique_feature_raises_on_missing_constitution(self, tmp_path):
        """critique_feature raises ConstitutionMissingError when file is absent."""
        missing = tmp_path / "nonexistent_constitution.md"
        assert not missing.exists()

        with pytest.raises(ConstitutionMissingError):
            critique_feature(
                feature_id="test-001",
                name="Test feature",
                description="d",
                acceptance_criteria=["File exists: src/x.py"],
                constitution_path=missing,
            )

    def test_constitution_missing_error_is_file_not_found(self, tmp_path):
        """ConstitutionMissingError is a subclass of FileNotFoundError."""
        missing = tmp_path / "absent.md"
        with pytest.raises(FileNotFoundError):
            critique_feature(
                feature_id="test-002",
                name="N",
                description="d",
                acceptance_criteria=[],
                constitution_path=missing,
            )

    def test_error_message_mentions_path(self, tmp_path):
        """The error message includes the missing file path."""
        missing = tmp_path / "no_constitution.md"
        with pytest.raises(ConstitutionMissingError) as exc_info:
            critique_feature(
                feature_id="test-003",
                name="N",
                description="d",
                acceptance_criteria=[],
                constitution_path=missing,
            )
        assert "spec_constitution" in str(exc_info.value).lower() or str(missing) in str(exc_info.value)

    def test_handle_empty_constitution_raises_on_missing_file(self, tmp_path):
        """handle_empty_constitution raises ConstitutionMissingError when absent."""
        missing = tmp_path / "no_constitution.md"
        with pytest.raises(ConstitutionMissingError):
            handle_empty_constitution(missing)

    def test_handle_empty_constitution_succeeds_when_file_exists(self, tmp_path):
        """handle_empty_constitution does not raise when the file exists."""
        constitution = tmp_path / "spec_constitution.md"
        constitution.write_text('version: "test"\n## P1\nsome content\n')
        handle_empty_constitution(constitution)  # must not raise

    def test_critique_feature_succeeds_with_valid_constitution(self, tmp_path):
        """critique_feature does not raise when constitution file exists."""
        constitution = tmp_path / "spec_constitution.md"
        constitution.write_text('version: "1.0"\n## P1\nsome content\n')
        # Should not raise
        defects = critique_feature(
            feature_id="test-004",
            name="N",
            description="d",
            acceptance_criteria=[
                "File exists: src/x.py",
                "pytest: tests/test_x_error.py",
            ],
            constitution_path=constitution,
        )
        assert isinstance(defects, list)
