"""Tests for run_mutation_test and related gate infrastructure — AC-14."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob3.verification.mutation_gate import (
    MutationReport,
    MutmutMissingError,
    default_threshold,
    run_mutation_test,
)


class TestRunMutationTestRaisesWhenMutmutMissing:
    def test_raises_mutmut_missing_error_when_not_on_path(self, tmp_path):
        with patch("bob3.verification.mutation_gate.shutil.which", return_value=None):
            with pytest.raises(MutmutMissingError) as exc_info:
                run_mutation_test(
                    feature_id="test-feat",
                    src_files=[],
                    test_dir=tmp_path,
                    workspace=tmp_path,
                )
            assert "mutmut" in str(exc_info.value).lower()

    def test_error_message_names_mutmut_package(self, tmp_path):
        with patch("bob3.verification.mutation_gate.shutil.which", return_value=None):
            with pytest.raises(MutmutMissingError) as exc_info:
                run_mutation_test("feat", [], tmp_path, tmp_path)
            assert "mutmut" in str(exc_info.value)


class TestRunMutationTestReturnsMutationReport:
    def test_returns_mutation_report_instance(self, tmp_path):
        # Patch subprocess so we don't actually run mutmut
        with patch("bob3.verification.mutation_gate.subprocess.Popen") as mock_popen, \
             patch("bob3.verification.mutation_gate._parse_mutmut_results") as mock_parse, \
             patch("bob3.verification.mutation_gate._collect_surviving_diffs") as mock_diffs:
            proc = MagicMock()
            proc.communicate.return_value = (b"", b"")
            proc.poll.return_value = 0
            mock_popen.return_value = proc
            mock_parse.return_value = {"total": 10, "killed": 8, "survived": 2, "timeout": 0}
            mock_diffs.return_value = []

            report = run_mutation_test(
                feature_id="feat-123",
                src_files=["src/foo.py"],
                test_dir=tmp_path,
                workspace=tmp_path,
            )

        assert isinstance(report, MutationReport)
        assert report.feature_id == "feat-123"
        assert report.total_mutants == 10
        assert report.killed == 8
        assert report.survived == 2
        assert report.mutation_score == pytest.approx(0.8)

    def test_mutation_score_is_killed_over_total(self, tmp_path):
        with patch("bob3.verification.mutation_gate.subprocess.Popen") as mock_popen, \
             patch("bob3.verification.mutation_gate._parse_mutmut_results") as mock_parse, \
             patch("bob3.verification.mutation_gate._collect_surviving_diffs") as mock_diffs:
            proc = MagicMock()
            proc.communicate.return_value = (b"", b"")
            proc.poll.return_value = 0
            mock_popen.return_value = proc
            mock_parse.return_value = {"total": 4, "killed": 3, "survived": 1, "timeout": 0}
            mock_diffs.return_value = []

            report = run_mutation_test("f", ["src/x.py"], tmp_path, tmp_path)

        assert report.mutation_score == pytest.approx(3 / 4)

    def test_score_is_1_when_no_mutants(self, tmp_path):
        with patch("bob3.verification.mutation_gate.subprocess.Popen") as mock_popen, \
             patch("bob3.verification.mutation_gate._parse_mutmut_results") as mock_parse, \
             patch("bob3.verification.mutation_gate._collect_surviving_diffs") as mock_diffs:
            proc = MagicMock()
            proc.communicate.return_value = (b"", b"")
            proc.poll.return_value = 0
            mock_popen.return_value = proc
            mock_parse.return_value = {"total": 0, "killed": 0, "survived": 0, "timeout": 0}
            mock_diffs.return_value = []

            report = run_mutation_test("f", [], tmp_path, tmp_path)

        assert report.mutation_score == pytest.approx(1.0)
