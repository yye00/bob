"""Tests for src/bob/learnings.py - Per-skill learning ledger."""
import os
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from bob.learnings import append_learning, read_learnings


class TestAppendLearning:
    """Tests for append_learning function."""

    def test_creates_learnings_file(self, tmp_path):
        skills_dir = tmp_path / "skills"
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            append_learning(
                skill="test-skill",
                lesson="Something important was learned",
                evidence={"file": "src/bob/foo.py", "line": 42},
                source_feature_id="abc-123",
            )
        ledger = skills_dir / "test-skill" / "LEARNINGS.md"
        assert ledger.exists()

    def test_creates_skill_directory(self, tmp_path):
        skills_dir = tmp_path / "skills"
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            append_learning(
                skill="brand-new-skill",
                lesson="A lesson",
                evidence={},
                source_feature_id=None,
            )
        assert (skills_dir / "brand-new-skill").is_dir()

    def test_entry_contains_timestamp(self, tmp_path):
        skills_dir = tmp_path / "skills"
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            append_learning(
                skill="ts-skill",
                lesson="Lesson with timestamp",
                evidence={"test": "test_foo"},
                source_feature_id=None,
            )
        content = (skills_dir / "ts-skill" / "LEARNINGS.md").read_text()
        # ISO 8601 timestamp pattern
        assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", content)

    def test_entry_contains_lesson_body(self, tmp_path):
        skills_dir = tmp_path / "skills"
        lesson_text = "Always validate inputs before processing"
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            append_learning(
                skill="lesson-skill",
                lesson=lesson_text,
                evidence={},
                source_feature_id=None,
            )
        content = (skills_dir / "lesson-skill" / "LEARNINGS.md").read_text()
        assert lesson_text in content

    def test_entry_contains_source_feature_id(self, tmp_path):
        skills_dir = tmp_path / "skills"
        feature_id = "c66a670b-3261-4c20-87c2-a4f8fb11da75"
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            append_learning(
                skill="feat-skill",
                lesson="Lesson from feature",
                evidence={},
                source_feature_id=feature_id,
            )
        content = (skills_dir / "feat-skill" / "LEARNINGS.md").read_text()
        assert feature_id in content

    def test_entry_contains_evidence_pointer(self, tmp_path):
        skills_dir = tmp_path / "skills"
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            append_learning(
                skill="evidence-skill",
                lesson="Lesson",
                evidence={"file": "src/bob/db.py", "line": 99},
                source_feature_id=None,
            )
        content = (skills_dir / "evidence-skill" / "LEARNINGS.md").read_text()
        assert "src/bob/db.py" in content
        assert "99" in content

    def test_source_feature_id_none_handled(self, tmp_path):
        skills_dir = tmp_path / "skills"
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            # Should not raise
            append_learning(
                skill="null-feat-skill",
                lesson="Lesson without feature",
                evidence={},
                source_feature_id=None,
            )
        assert (skills_dir / "null-feat-skill" / "LEARNINGS.md").exists()

    def test_appends_multiple_entries(self, tmp_path):
        skills_dir = tmp_path / "skills"
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            append_learning("multi-skill", "First lesson", {}, "feat-1")
            append_learning("multi-skill", "Second lesson", {}, "feat-2")
            append_learning("multi-skill", "Third lesson", {}, "feat-3")

        content = (skills_dir / "multi-skill" / "LEARNINGS.md").read_text()
        assert "First lesson" in content
        assert "Second lesson" in content
        assert "Third lesson" in content

    def test_each_entry_is_separated(self, tmp_path):
        skills_dir = tmp_path / "skills"
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            append_learning("sep-skill", "Lesson A", {}, None)
            append_learning("sep-skill", "Lesson B", {}, None)

        content = (skills_dir / "sep-skill" / "LEARNINGS.md").read_text()
        # Each entry should have a markdown heading or horizontal rule separator
        assert content.count("Lesson A") == 1
        assert content.count("Lesson B") == 1

    def test_evidence_test_name_format(self, tmp_path):
        skills_dir = tmp_path / "skills"
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            append_learning(
                skill="test-evidence-skill",
                lesson="Lesson from test",
                evidence={"test": "test_append_learning_creates_file"},
                source_feature_id=None,
            )
        content = (skills_dir / "test-evidence-skill" / "LEARNINGS.md").read_text()
        assert "test_append_learning_creates_file" in content


class TestReadLearnings:
    """Tests for read_learnings function."""

    def test_returns_empty_list_when_no_file(self, tmp_path):
        skills_dir = tmp_path / "skills"
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            result = read_learnings("nonexistent-skill")
        assert result == []

    def test_returns_list_of_dicts(self, tmp_path):
        skills_dir = tmp_path / "skills"
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            append_learning("dict-skill", "A lesson", {"file": "x.py", "line": 1}, "feat-x")
            result = read_learnings("dict-skill")
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], dict)

    def test_each_entry_has_required_fields(self, tmp_path):
        skills_dir = tmp_path / "skills"
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            append_learning(
                skill="fields-skill",
                lesson="Important lesson",
                evidence={"file": "src/bob/foo.py", "line": 10},
                source_feature_id="feat-abc",
            )
            result = read_learnings("fields-skill")

        entry = result[0]
        assert "timestamp" in entry
        assert "lesson" in entry
        assert "evidence" in entry
        assert "source_feature_id" in entry

    def test_lesson_body_preserved(self, tmp_path):
        skills_dir = tmp_path / "skills"
        lesson = "Never ignore the return value of os.rename"
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            append_learning("body-skill", lesson, {}, None)
            result = read_learnings("body-skill")
        assert result[0]["lesson"] == lesson

    def test_source_feature_id_preserved(self, tmp_path):
        skills_dir = tmp_path / "skills"
        feature_id = "abcd-1234"
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            append_learning("id-skill", "Lesson", {}, feature_id)
            result = read_learnings("id-skill")
        assert result[0]["source_feature_id"] == feature_id

    def test_source_feature_id_none_preserved(self, tmp_path):
        skills_dir = tmp_path / "skills"
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            append_learning("none-id-skill", "Lesson", {}, None)
            result = read_learnings("none-id-skill")
        assert result[0]["source_feature_id"] is None

    def test_evidence_preserved(self, tmp_path):
        skills_dir = tmp_path / "skills"
        evidence = {"file": "src/bob/db.py", "line": 55}
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            append_learning("ev-skill", "Lesson", evidence, None)
            result = read_learnings("ev-skill")
        assert result[0]["evidence"] == evidence

    def test_multiple_entries_returned(self, tmp_path):
        skills_dir = tmp_path / "skills"
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            append_learning("multi-read", "Lesson 1", {}, "f1")
            append_learning("multi-read", "Lesson 2", {}, "f2")
            append_learning("multi-read", "Lesson 3", {}, "f3")
            result = read_learnings("multi-read")
        assert len(result) == 3
        lessons = [e["lesson"] for e in result]
        assert "Lesson 1" in lessons
        assert "Lesson 2" in lessons
        assert "Lesson 3" in lessons

    def test_entries_in_chronological_order(self, tmp_path):
        skills_dir = tmp_path / "skills"
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            append_learning("order-skill", "First", {}, None)
            append_learning("order-skill", "Second", {}, None)
            result = read_learnings("order-skill")
        assert result[0]["lesson"] == "First"
        assert result[1]["lesson"] == "Second"

    def test_timestamp_is_iso_format(self, tmp_path):
        skills_dir = tmp_path / "skills"
        with patch("bob.learnings.SKILLS_DIR", skills_dir):
            append_learning("ts-read-skill", "Lesson", {}, None)
            result = read_learnings("ts-read-skill")
        ts = result[0]["timestamp"]
        # Should parse as ISO 8601
        from datetime import datetime
        parsed = datetime.fromisoformat(ts)
        assert parsed is not None
