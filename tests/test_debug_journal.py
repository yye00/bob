"""Tests for the MemGPT-style debug journal."""

import pytest
from pathlib import Path

from bob.orchestrator.debug_journal import DebugJournal, _truncate


class TestDebugJournal:
    """Test debug journal creation and retrieval."""

    def test_create_journal_on_first_attempt(self, tmp_path):
        journal = DebugJournal(tmp_path)
        assert not journal.has_journal("D003")

        journal.record_attempt(
            spec_id="D003",
            task_title="Two-Site Optimizer",
            attempt_number=1,
            verification_error="ValueError: shapes (2,4,2) and (4,2) not aligned",
        )

        assert journal.has_journal("D003")
        assert journal.get_attempt_count("D003") == 1

    def test_multiple_attempts(self, tmp_path):
        journal = DebugJournal(tmp_path)

        journal.record_attempt(
            spec_id="D003",
            task_title="Two-Site Optimizer",
            attempt_number=1,
            verification_error="ValueError: shapes (2,4,2) not aligned",
        )
        journal.record_attempt(
            spec_id="D003",
            task_title="Two-Site Optimizer",
            attempt_number=2,
            verification_error="Energy -0.586 but expected < -3.0",
            approach_taken="Fixed SVD truncation",
        )
        journal.record_attempt(
            spec_id="D003",
            task_title="Two-Site Optimizer",
            attempt_number=3,
            verification_error="chi_right=2 != chi_left=4",
            files_modified=["src/distributed/optimizer.py"],
        )

        assert journal.get_attempt_count("D003") == 3

    def test_compact_summary(self, tmp_path):
        journal = DebugJournal(tmp_path)

        journal.record_attempt(
            spec_id="D003",
            task_title="Two-Site Optimizer",
            attempt_number=1,
            verification_error="ValueError: shapes (2,4,2) and (4,2) not aligned\nTraceback...\n  File optimizer.py line 342",
        )
        journal.record_attempt(
            spec_id="D003",
            task_title="Two-Site Optimizer",
            attempt_number=2,
            verification_error="FAIL: Energy -0.586 but expected < -3.0",
        )

        summary = journal.get_compact_summary("D003")

        # Should be compact — a few lines, not hundreds
        assert len(summary) < 500  # Under 500 chars
        assert "Previous debug attempts" in summary
        assert "2 total" in summary
        # Should reference the journal file
        assert ".bob/debug/D003.md" in summary

    def test_compact_summary_empty(self, tmp_path):
        journal = DebugJournal(tmp_path)
        assert journal.get_compact_summary("nonexistent") == ""

    def test_record_success(self, tmp_path):
        journal = DebugJournal(tmp_path)

        journal.record_attempt(
            spec_id="D003",
            task_title="Two-Site Optimizer",
            attempt_number=1,
            verification_error="Energy too high",
        )
        journal.record_success("D003", 2)

        content = journal.get_full_journal("D003")
        assert "RESOLVED" in content
        assert "2 debug attempt" in content

    def test_clear_journal(self, tmp_path):
        journal = DebugJournal(tmp_path)

        journal.record_attempt(
            spec_id="D003",
            task_title="Test",
            attempt_number=1,
            verification_error="error",
        )
        assert journal.has_journal("D003")

        journal.clear_journal("D003")
        assert not journal.has_journal("D003")

    def test_list_journals(self, tmp_path):
        journal = DebugJournal(tmp_path)

        journal.record_attempt("D001", "MPS", 1, "error 1")
        journal.record_attempt("D003", "Optimizer", 1, "error 2")
        journal.record_attempt("D003", "Optimizer", 2, "error 3")
        journal.record_success("D001", 1)

        journals = journal.list_journals()
        assert len(journals) == 2

        d001 = next(j for j in journals if j["spec_id"] == "D001")
        assert d001["attempts"] == 1
        assert d001["resolved"] is True

        d003 = next(j for j in journals if j["spec_id"] == "D003")
        assert d003["attempts"] == 2
        assert d003["resolved"] is False

    def test_journal_path_sanitization(self, tmp_path):
        journal = DebugJournal(tmp_path)
        path = journal.journal_path("task/with/slashes")
        assert "task_with_slashes" in path.name

    def test_auto_summarize_traceback(self, tmp_path):
        journal = DebugJournal(tmp_path)

        error = """Traceback (most recent call last):
  File "optimizer.py", line 342, in left_canonicalize_mps
    result = np.tensordot(a, b, axes=([1], [0]))
ValueError: shapes (2,4,2) and (4,2) not aligned"""

        journal.record_attempt("T1", "Test", 1, error)

        summary = journal.get_compact_summary("T1")
        # Should extract the ValueError line, not the full traceback
        assert "ValueError" in summary
        assert "Traceback" not in summary

    def test_auto_summarize_fail_line(self, tmp_path):
        journal = DebugJournal(tmp_path)

        error = """Running verification...
Checking energy convergence...
FAIL: Energy -0.586 does not meet threshold < -3.0
Expected Heisenberg ground state energy"""

        journal.record_attempt("T1", "Test", 1, error)

        summary = journal.get_compact_summary("T1")
        assert "FAIL" in summary

    def test_multiple_tasks_independent(self, tmp_path):
        journal = DebugJournal(tmp_path)

        journal.record_attempt("D001", "MPS", 1, "error A")
        journal.record_attempt("D003", "Optimizer", 1, "error B")

        assert journal.get_attempt_count("D001") == 1
        assert journal.get_attempt_count("D003") == 1
        assert "error A" in journal.get_full_journal("D001")
        assert "error B" in journal.get_full_journal("D003")
        assert "error A" not in journal.get_full_journal("D003")


class TestTruncate:
    def test_short_text(self):
        assert _truncate("hello", 10) == "hello"

    def test_long_text(self):
        result = _truncate("a" * 200, 50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_exact_length(self):
        assert _truncate("hello", 5) == "hello"
