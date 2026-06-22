"""Tests for bob3.structural_log_line_ac_handler_x_py_emits_string_log_line (feature f78ce68d).

Verifies that the delegation module correctly surfaces the structural log-line
AC handler that tolerates Python adjacent-string-literal concat across newlines.

Covered scenarios:
- Exact literal present in file → True
- STRING split across Python adjacent-string-literal concat → True after join
- All tokens present in order but not contiguous → True via token-order fallback
- STRING missing → None (fall-through, no silent over-demotion)
- Non-"emits" criterion → None (not our pattern)
- File does not exist → None
"""

from __future__ import annotations

import pathlib

import pytest

from bob3.structural_log_line_ac_handler_x_py_emits_string_log_line import (
    structural_log_line_ac_handler_x_py_emits_string_log_line,
)


def _write_src(tmp_path: pathlib.Path, content: str, rel: str = "src/bob3/run_loop.py") -> pathlib.Path:
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return tmp_path


def test_structural_log_line_ac_handler_x_py_emits_string_log_line(tmp_path):
    """AC entry point: the public function exists and returns True for a matching criterion."""
    src = 'logger.info("Run finished: termination=%s")\n'
    workspace = _write_src(tmp_path, src)
    result = structural_log_line_ac_handler_x_py_emits_string_log_line(
        criterion_body="src/bob3/run_loop.py emits a 'Run finished: termination=%s' log line",
        workspace=workspace,
    )
    assert result is True


def test_exact_match_returns_true(tmp_path):
    """When the log string is present verbatim, return True."""
    src = (
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        'logger.info("Run finished: termination=%s features_completed=%d")\n'
    )
    workspace = _write_src(tmp_path, src)
    result = structural_log_line_ac_handler_x_py_emits_string_log_line(
        criterion_body="src/bob3/run_loop.py emits a 'Run finished: termination=%s' log line",
        workspace=workspace,
    )
    assert result is True


def test_adjacent_literal_concat_returns_true(tmp_path):
    """When the log string is split across adjacent Python string literals, return True."""
    src = (
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "\n"
        "def finish(termination):\n"
        '    logger.info(\n'
        '        "Run finished: termination=%s "\n'
        '        "features_completed=%d",\n'
        '        termination,\n'
        '    )\n'
    )
    workspace = _write_src(tmp_path, src)
    result = structural_log_line_ac_handler_x_py_emits_string_log_line(
        criterion_body="src/bob3/run_loop.py emits a 'Run finished: termination=%s' log line",
        workspace=workspace,
    )
    assert result is True


def test_token_order_fallback_returns_true(tmp_path):
    """When all tokens of the log string are present but not contiguous, return True (token fallback)."""
    # Tokens: Run, finished:, termination=%s — each present but not as one literal
    src = (
        "# Run\n"
        "# finished:\n"
        '# termination=%s\n'
        'logger.info("something termination=%s")\n'
        '# Run finished: extra text termination=%s\n'
    )
    workspace = _write_src(tmp_path, src)
    result = structural_log_line_ac_handler_x_py_emits_string_log_line(
        criterion_body="src/bob3/run_loop.py emits a 'Run finished: termination=%s' log line",
        workspace=workspace,
    )
    assert result is True


def test_missing_string_returns_none(tmp_path):
    """When the log string and its tokens are absent, return None (fall-through)."""
    src = (
        "import logging\n"
        'logger.info("Completely different message")\n'
    )
    workspace = _write_src(tmp_path, src)
    result = structural_log_line_ac_handler_x_py_emits_string_log_line(
        criterion_body="src/bob3/run_loop.py emits a 'Run finished: termination=%s' log line",
        workspace=workspace,
    )
    assert result is None


def test_non_emits_criterion_returns_none(tmp_path):
    """When the criterion body does not match the 'X.py emits' pattern, return None."""
    src = "def some_function(): pass\n"
    workspace = _write_src(tmp_path, src)
    result = structural_log_line_ac_handler_x_py_emits_string_log_line(
        criterion_body="src/bob3/run_loop.py defines function some_function",
        workspace=workspace,
    )
    assert result is None


def test_file_does_not_exist_returns_none(tmp_path):
    """When the referenced .py file does not exist, return None."""
    result = structural_log_line_ac_handler_x_py_emits_string_log_line(
        criterion_body="src/bob3/nonexistent_module.py emits a 'Some log line' log line",
        workspace=tmp_path,
    )
    assert result is None


def test_with_quote_style_variants(tmp_path):
    """Criterion using double-quotes around the log string is also accepted."""
    src = 'logger.info("Queue drained — all features terminal")\n'
    workspace = _write_src(tmp_path, src)
    result = structural_log_line_ac_handler_x_py_emits_string_log_line(
        criterion_body='src/bob3/run_loop.py emits a "Queue drained" log line',
        workspace=workspace,
    )
    assert result is True


def test_different_file_path(tmp_path):
    """Handler resolves paths relative to workspace for any .py file."""
    src = 'logger.info("Heartbeat: pid=%d")\n'
    workspace = _write_src(tmp_path, src, rel="src/bob3/orchestrator/run_loop.py")
    result = structural_log_line_ac_handler_x_py_emits_string_log_line(
        criterion_body="src/bob3/orchestrator/run_loop.py emits a 'Heartbeat: pid=%d' log line",
        workspace=workspace,
    )
    assert result is True
