"""Tests for F108: Progress notes between sessions (claude-progress.txt).

Tests the progress notes system that provides session continuity by writing
structured entries to claude-progress.txt after each sub-agent session.
Each entry records feature outcomes, blockers, and session context. The file
keeps only the last 10 entries to avoid unbounded growth.
"""

import os
import pathlib
import textwrap

import pytest

from bob3.orientation import (
    update_progress_notes,
    read_progress_notes,
    format_progress_entry,
    MAX_PROGRESS_ENTRIES,
)


# ============================================================
# Step 1: format_progress_entry produces a well-formed entry
# ============================================================


class TestFormatProgressEntry:
    """Test formatting of individual progress entries."""

    def test_returns_string(self):
        entry = format_progress_entry(
            feature_id="F108",
            feature_name="Progress notes",
            outcome="completed",
            duration_ms=5000,
            num_turns=10,
            cost_usd=0.50,
        )
        assert isinstance(entry, str)

    def test_includes_feature_id(self):
        entry = format_progress_entry(
            feature_id="F108",
            feature_name="Progress notes",
            outcome="completed",
        )
        assert "F108" in entry

    def test_includes_feature_name(self):
        entry = format_progress_entry(
            feature_id="F108",
            feature_name="Progress notes",
            outcome="completed",
        )
        assert "Progress notes" in entry

    def test_includes_outcome(self):
        entry = format_progress_entry(
            feature_id="F108",
            feature_name="Progress notes",
            outcome="failed",
        )
        assert "failed" in entry

    def test_includes_timestamp(self):
        entry = format_progress_entry(
            feature_id="F108",
            feature_name="Progress notes",
            outcome="completed",
        )
        # Should have a timestamp with UTC
        assert "UTC" in entry or "timestamp" in entry

    def test_includes_duration_when_provided(self):
        entry = format_progress_entry(
            feature_id="F108",
            feature_name="Progress notes",
            outcome="completed",
            duration_ms=123456,
        )
        assert "123456" in entry

    def test_includes_cost_when_provided(self):
        entry = format_progress_entry(
            feature_id="F108",
            feature_name="Progress notes",
            outcome="completed",
            cost_usd=1.2345,
        )
        assert "1.2345" in entry

    def test_includes_num_turns_when_provided(self):
        entry = format_progress_entry(
            feature_id="F108",
            feature_name="Progress notes",
            outcome="completed",
            num_turns=42,
        )
        assert "42" in entry

    def test_includes_blockers_when_provided(self):
        entry = format_progress_entry(
            feature_id="F108",
            feature_name="Progress notes",
            outcome="failed",
            blockers="Missing dependency on F107",
        )
        assert "Missing dependency on F107" in entry

    def test_includes_notes_when_provided(self):
        entry = format_progress_entry(
            feature_id="F108",
            feature_name="Progress notes",
            outcome="completed",
            notes="Implemented TDD approach",
        )
        assert "Implemented TDD approach" in entry

    def test_entries_separated_by_triple_dash(self):
        """Entries should end with --- separator for parsing."""
        entry = format_progress_entry(
            feature_id="F108",
            feature_name="Progress notes",
            outcome="completed",
        )
        assert entry.strip().endswith("---")


# ============================================================
# Step 2: update_progress_notes writes to file
# ============================================================


class TestUpdateProgressNotes:
    """Test writing progress notes to claude-progress.txt."""

    def test_creates_file_if_not_exists(self, tmp_path):
        progress_file = tmp_path / "claude-progress.txt"
        assert not progress_file.exists()

        update_progress_notes(
            workspace=str(tmp_path),
            feature_id="F108",
            feature_name="Progress notes",
            outcome="completed",
        )

        assert progress_file.exists()

    def test_writes_entry_to_file(self, tmp_path):
        update_progress_notes(
            workspace=str(tmp_path),
            feature_id="F108",
            feature_name="Progress notes",
            outcome="completed",
        )

        content = (tmp_path / "claude-progress.txt").read_text()
        assert "F108" in content
        assert "Progress notes" in content
        assert "completed" in content

    def test_appends_to_existing_file(self, tmp_path):
        # Write first entry
        update_progress_notes(
            workspace=str(tmp_path),
            feature_id="F001",
            feature_name="First feature",
            outcome="completed",
        )

        # Write second entry
        update_progress_notes(
            workspace=str(tmp_path),
            feature_id="F002",
            feature_name="Second feature",
            outcome="completed",
        )

        content = (tmp_path / "claude-progress.txt").read_text()
        assert "F001" in content
        assert "F002" in content

    def test_includes_optional_fields(self, tmp_path):
        update_progress_notes(
            workspace=str(tmp_path),
            feature_id="F108",
            feature_name="Progress notes",
            outcome="failed",
            duration_ms=5000,
            num_turns=10,
            cost_usd=0.50,
            blockers="Test failure in module X",
            notes="Need to investigate further",
        )

        content = (tmp_path / "claude-progress.txt").read_text()
        assert "5000" in content
        assert "0.5" in content
        assert "Test failure in module X" in content
        assert "Need to investigate further" in content


# ============================================================
# Step 3: Keep last 10 entries
# ============================================================


class TestProgressNotesLimit:
    """Test that progress notes are limited to MAX_PROGRESS_ENTRIES entries."""

    def test_max_entries_constant_is_10(self):
        assert MAX_PROGRESS_ENTRIES == 10

    def test_keeps_only_last_10_entries(self, tmp_path):
        # Write 12 entries
        for i in range(12):
            update_progress_notes(
                workspace=str(tmp_path),
                feature_id=f"F{i:03d}",
                feature_name=f"Feature {i}",
                outcome="completed",
            )

        content = (tmp_path / "claude-progress.txt").read_text()

        # First two entries (F000, F001) should be trimmed
        assert "F000" not in content
        assert "F001" not in content

        # Last 10 entries (F002-F011) should still be present
        assert "F002" in content
        assert "F011" in content

    def test_exactly_10_entries_not_trimmed(self, tmp_path):
        for i in range(10):
            update_progress_notes(
                workspace=str(tmp_path),
                feature_id=f"F{i:03d}",
                feature_name=f"Feature {i}",
                outcome="completed",
            )

        content = (tmp_path / "claude-progress.txt").read_text()
        # All 10 entries should be present
        assert "F000" in content
        assert "F009" in content

    def test_11th_entry_trims_first(self, tmp_path):
        for i in range(11):
            update_progress_notes(
                workspace=str(tmp_path),
                feature_id=f"F{i:03d}",
                feature_name=f"Feature {i}",
                outcome="completed",
            )

        content = (tmp_path / "claude-progress.txt").read_text()
        # First entry (F000) should be trimmed
        assert "F000" not in content
        # All others should be present
        assert "F001" in content
        assert "F010" in content


# ============================================================
# Step 4: read_progress_notes returns file contents
# ============================================================


class TestReadProgressNotes:
    """Test reading progress notes from claude-progress.txt."""

    def test_returns_empty_string_when_file_missing(self, tmp_path):
        result = read_progress_notes(workspace=str(tmp_path))
        assert result == ""

    def test_returns_file_content(self, tmp_path):
        update_progress_notes(
            workspace=str(tmp_path),
            feature_id="F108",
            feature_name="Progress notes",
            outcome="completed",
        )

        result = read_progress_notes(workspace=str(tmp_path))
        assert "F108" in result
        assert "Progress notes" in result

    def test_returns_all_entries(self, tmp_path):
        update_progress_notes(
            workspace=str(tmp_path),
            feature_id="F001",
            feature_name="First feature",
            outcome="completed",
        )
        update_progress_notes(
            workspace=str(tmp_path),
            feature_id="F002",
            feature_name="Second feature",
            outcome="failed",
        )

        result = read_progress_notes(workspace=str(tmp_path))
        assert "F001" in result
        assert "F002" in result


# ============================================================
# Step 5: Integration - orientation prompt includes notes
# ============================================================


class TestOrientationIncludesNotes:
    """Test that the orientation prompt references progress notes."""

    def test_orientation_mentions_progress_file(self):
        """The orientation prompt should mention reading claude-progress.txt."""
        from bob3.orientation import get_orientation_prompt

        result = get_orientation_prompt(
            feature_id="F108",
            workspace="/tmp/test-workspace",
        )
        assert "claude-progress" in result
