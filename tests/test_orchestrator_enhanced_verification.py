"""Tests for bob.orchestrator.enhanced_verification.verify_structural_log_line.

AC: "pytest: tests/test_orchestrator_enhanced_verification.py"
Feature: 0a898414-1b37-4a43-b65b-a2f7a447abd0

Covers:
- verify_structural_log_line is importable from bob.orchestrator.enhanced_verification
- Exact literal present in file → True
- Adjacent-string-literal concat across newlines → True after join
- Token-order fallback (all tokens present in order) → True
- Log string missing → None (fall-through)
- Non-emits criterion → None
- File does not exist → None
- Invalid criterion_body type → ValueError
- Invalid workspace type → ValueError
"""

from __future__ import annotations

import pathlib

import pytest

from bob.orchestrator.enhanced_verification import verify_structural_log_line


def _write_src(tmp_path: pathlib.Path, content: str, rel: str = "src/bob/orchestrator/run_loop.py") -> pathlib.Path:
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return tmp_path


class TestVerifyStructuralLogLineImport:
    """Function is importable and callable."""

    def test_function_exists(self):
        assert callable(verify_structural_log_line)

    def test_returns_none_for_non_matching_criterion(self, tmp_path):
        result = verify_structural_log_line(
            criterion_body="defines function bar",
            workspace=tmp_path,
        )
        assert result is None


class TestExactMatch:
    """Exact literal present in raw file content → True."""

    def test_exact_match_returns_true(self, tmp_path):
        workspace = _write_src(
            tmp_path,
            'logger.info("Run finished: termination=%s")\n',
        )
        result = verify_structural_log_line(
            criterion_body="src/bob/orchestrator/run_loop.py emits a 'Run finished: termination=%s' log line",
            workspace=workspace,
        )
        assert result is True

    def test_exact_match_double_quoted_criterion(self, tmp_path):
        workspace = _write_src(tmp_path, 'logger.info("Queue drained")\n')
        result = verify_structural_log_line(
            criterion_body='src/bob/orchestrator/run_loop.py emits a "Queue drained" log line',
            workspace=workspace,
        )
        assert result is True


class TestAdjacentLiteralConcat:
    """String split across Python adjacent-string-literal concat → True after join."""

    def test_adjacent_literal_split_returns_true(self, tmp_path):
        src = (
            "import logging\n"
            "logger = logging.getLogger(__name__)\n"
            "\n"
            "def finish(termination, completed, failed):\n"
            '    logger.info(\n'
            '        "Run finished: termination=%s "\n'
            '        "features_completed=%d",\n'
            '        termination,\n'
            '        completed,\n'
            '    )\n'
        )
        workspace = _write_src(tmp_path, src)
        result = verify_structural_log_line(
            criterion_body="src/bob/orchestrator/run_loop.py emits a 'Run finished: termination=%s' log line",
            workspace=workspace,
        )
        assert result is True

    def test_multiline_adjacent_literal_returns_true(self, tmp_path):
        src = (
            'logger.error(\n'
            '    "Queue drained — all features "\n'
            '    "terminal"\n'
            ')\n'
        )
        workspace = _write_src(tmp_path, src)
        result = verify_structural_log_line(
            criterion_body="src/bob/orchestrator/run_loop.py emits a 'Queue drained — all features' log line",
            workspace=workspace,
        )
        assert result is True


class TestTokenOrderFallback:
    """All tokens present in order → True (token-order fallback)."""

    def test_token_order_fallback_returns_true(self, tmp_path):
        # Tokens: "Run", "finished:", "termination=%s" all present in the file
        src = (
            "# Run\n"
            "# finished:\n"
            '# termination=%s\n'
            'logger.info("termination=%s Run finished: extra")\n'
        )
        workspace = _write_src(tmp_path, src)
        result = verify_structural_log_line(
            criterion_body="src/bob/orchestrator/run_loop.py emits a 'Run finished: termination=%s' log line",
            workspace=workspace,
        )
        assert result is True


class TestMissAndFallThrough:
    """Log string absent → None."""

    def test_missing_string_returns_none(self, tmp_path):
        workspace = _write_src(
            tmp_path,
            'logger.info("Completely different message")\n',
        )
        result = verify_structural_log_line(
            criterion_body="src/bob/orchestrator/run_loop.py emits a 'Run finished: termination=%s' log line",
            workspace=workspace,
        )
        assert result is None

    def test_non_emits_criterion_returns_none(self, tmp_path):
        workspace = _write_src(tmp_path, "def foo(): pass\n")
        result = verify_structural_log_line(
            criterion_body="src/bob/orchestrator/run_loop.py defines function foo",
            workspace=workspace,
        )
        assert result is None

    def test_file_does_not_exist_returns_none(self, tmp_path):
        result = verify_structural_log_line(
            criterion_body="src/bob/orchestrator/nonexistent.py emits a 'Some log' log line",
            workspace=tmp_path,
        )
        assert result is None

    def test_empty_criterion_returns_none(self, tmp_path):
        result = verify_structural_log_line(criterion_body="", workspace=tmp_path)
        assert result is None


class TestInvalidInputRaises:
    """Invalid types raise ValueError."""

    def test_none_criterion_body_raises(self, tmp_path):
        with pytest.raises(ValueError, match="criterion_body"):
            verify_structural_log_line(criterion_body=None, workspace=tmp_path)

    def test_int_criterion_body_raises(self, tmp_path):
        with pytest.raises(ValueError, match="criterion_body"):
            verify_structural_log_line(criterion_body=42, workspace=tmp_path)

    def test_none_workspace_raises(self, tmp_path):
        with pytest.raises(ValueError, match="workspace"):
            verify_structural_log_line(
                criterion_body="a.py emits a 'x' log line",
                workspace=None,
            )

    def test_string_workspace_raises(self, tmp_path):
        with pytest.raises(ValueError, match="workspace"):
            verify_structural_log_line(
                criterion_body="a.py emits a 'x' log line",
                workspace=str(tmp_path),
            )
