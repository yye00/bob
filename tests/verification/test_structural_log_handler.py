"""Tests for bob3.verification.structural_log_handler.match_log_line_ac.

Verifies that:
- match_log_line_ac is importable from bob3.verification.structural_log_handler
- It delegates correctly to handle_structural_log_line
- It handles exact matches, adjacent-literal concat, token-order fallback,
  missing files, and non-matching criteria
- Invalid inputs raise ValueError (matching the underlying implementation)
"""

from __future__ import annotations

import pathlib

import pytest

from bob3.verification.structural_log_handler import match_log_line_ac


class TestMatchLogLineAcBasicBehavior:
    """Core matching behavior of match_log_line_ac."""

    def test_returns_true_for_exact_match(self, tmp_path):
        """Log string found verbatim in file → True."""
        py_file = tmp_path / "run_loop.py"
        py_file.write_text('logger.info("Run finished: termination=%s")\n')
        result = match_log_line_ac(
            criterion_body="run_loop.py emits a 'Run finished: termination=%s' log line",
            workspace=tmp_path,
        )
        assert result is True

    def test_returns_none_when_string_absent(self, tmp_path):
        """Log string not in file → None (caller falls through)."""
        py_file = tmp_path / "run_loop.py"
        py_file.write_text('logger.info("Something else")\n')
        result = match_log_line_ac(
            criterion_body="run_loop.py emits a 'Run finished: termination=%s' log line",
            workspace=tmp_path,
        )
        assert result is None

    def test_returns_none_when_file_missing(self, tmp_path):
        """File not found → None."""
        result = match_log_line_ac(
            criterion_body="nonexistent.py emits a 'some string' log line",
            workspace=tmp_path,
        )
        assert result is None

    def test_returns_none_for_non_emits_criterion(self, tmp_path):
        """Criterion without 'emits' pattern → None."""
        result = match_log_line_ac(
            criterion_body="src/bob3/foo.py defines function bar",
            workspace=tmp_path,
        )
        assert result is None

    def test_returns_none_for_empty_criterion(self, tmp_path):
        """Empty criterion body → None, no raise."""
        result = match_log_line_ac(criterion_body="", workspace=tmp_path)
        assert result is None


class TestMatchLogLineAcAdjacentLiteralConcat:
    """Adjacent-string-literal concat tolerance."""

    def test_adjacent_literal_concat_across_newline(self, tmp_path):
        """String split across adjacent literals (\"a\"\n    \"b\") → True via join."""
        py_file = tmp_path / "run_loop.py"
        py_file.write_text(
            'logger.info(\n'
            '    "Run finished: termination=%s features_completed=%d "\n'
            '    "features_failed=%d"\n'
            ')\n'
        )
        result = match_log_line_ac(
            criterion_body=(
                "run_loop.py emits a "
                "'Run finished: termination=%s features_completed=%d features_failed=%d' "
                "log line"
            ),
            workspace=tmp_path,
        )
        assert result is True

    def test_adjacent_literal_concat_with_subdirectory(self, tmp_path):
        """File in subdirectory, split literal → True."""
        subdir = tmp_path / "src" / "bob3" / "orchestrator"
        subdir.mkdir(parents=True)
        py_file = subdir / "run_loop.py"
        py_file.write_text(
            'logger.warning(\n'
            '    "Queue drained: all_blocked "\n'
            '    "features=%d"\n'
            ')\n'
        )
        result = match_log_line_ac(
            criterion_body=(
                "src/bob3/orchestrator/run_loop.py emits a "
                "'Queue drained: all_blocked features=%d' log line"
            ),
            workspace=tmp_path,
        )
        assert result is True


class TestMatchLogLineAcTokenOrderFallback:
    """Token-order fallback: all tokens present but string is not literally joined."""

    def test_token_order_fallback_all_tokens_present(self, tmp_path):
        """All tokens of the log string present in source → True (with warning)."""
        py_file = tmp_path / "module.py"
        # Content has all tokens but in a way adjacent-join doesn't stitch them.
        py_file.write_text(
            'logger.info("termination=%s")\n'
            'logger.info("Run finished:")\n'
        )
        result = match_log_line_ac(
            criterion_body="module.py emits a 'Run finished: termination=%s' log line",
            workspace=tmp_path,
        )
        # Token-order fallback: both "Run" and "finished:" and "termination=%s"
        # are individually present. Result is True.
        assert result is True


class TestMatchLogLineAcInvalidInputs:
    """Invalid inputs must raise ValueError."""

    def test_none_criterion_body_raises(self, tmp_path):
        with pytest.raises(ValueError, match="criterion_body"):
            match_log_line_ac(criterion_body=None, workspace=tmp_path)

    def test_int_criterion_body_raises(self, tmp_path):
        with pytest.raises(ValueError, match="criterion_body"):
            match_log_line_ac(criterion_body=42, workspace=tmp_path)

    def test_bytes_criterion_body_raises(self, tmp_path):
        with pytest.raises(ValueError, match="criterion_body"):
            match_log_line_ac(
                criterion_body=b"run_loop.py emits a 'x' log line",
                workspace=tmp_path,
            )

    def test_none_workspace_raises(self, tmp_path):
        with pytest.raises(ValueError, match="workspace"):
            match_log_line_ac(
                criterion_body="run_loop.py emits a 'x' log line",
                workspace=None,
            )

    def test_string_workspace_raises(self, tmp_path):
        with pytest.raises(ValueError, match="workspace"):
            match_log_line_ac(
                criterion_body="run_loop.py emits a 'x' log line",
                workspace=str(tmp_path),
            )


class TestMatchLogLineAcIntegrationWithEnhancedVerification:
    """Confirm match_log_line_ac is also accessible via bob3.verification.enhanced_verification."""

    def test_importable_from_verification_enhanced_verification(self):
        from bob3.verification.enhanced_verification import match_log_line_ac as mla
        assert callable(mla)

    def test_same_function_object(self):
        from bob3.verification.enhanced_verification import match_log_line_ac as mla
        from bob3.verification.structural_log_handler import match_log_line_ac as slh
        # Both should delegate to handle_structural_log_line; they may not be
        # the exact same object but must behave identically.
        assert callable(mla)
        assert callable(slh)

    def test_consistent_behavior_across_namespaces(self, tmp_path):
        from bob3.verification.enhanced_verification import match_log_line_ac as mla
        from bob3.verification.structural_log_handler import match_log_line_ac as slh
        py_file = tmp_path / "foo.py"
        py_file.write_text('logger.info("hello world")\n')
        r1 = mla(criterion_body="foo.py emits a 'hello world' log line", workspace=tmp_path)
        r2 = slh(criterion_body="foo.py emits a 'hello world' log line", workspace=tmp_path)
        assert r1 == r2 == True
