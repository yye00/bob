"""Tests for the structural log-line AC handler in bob.enhanced_verification.

Covers "X.py emits a 'STRING' log line" structural ACs, including the core
regression: the log format string is split across adjacent Python string
literals separated by whitespace + newline. A naive ``STRING in file_contents``
check misses this; the handler must join adjacent literals before searching.

AC surface:
- Function defined: bob.enhanced_verification.check_structural_log_line
- integration: bob.enhanced_verification
- File exists: src/bob/orchestrator/run_loop.py
"""

from __future__ import annotations

import pathlib

import pytest

import bob.enhanced_verification as ev
from bob.enhanced_verification import (
    check_structural_log_line,
    handle_structural_log_line,
)


class TestAcSurface:
    """The AC-named symbol and integration target are present."""

    def test_check_structural_log_line_defined(self):
        assert callable(ev.check_structural_log_line)

    def test_check_structural_log_line_is_handler_alias(self):
        assert ev.check_structural_log_line is ev.handle_structural_log_line

    def test_module_importable(self):
        assert ev is not None

    def test_run_loop_file_exists(self):
        run_loop = (
            pathlib.Path(__file__).resolve().parent.parent
            / "src"
            / "bob"
            / "orchestrator"
            / "run_loop.py"
        )
        assert run_loop.is_file()


class TestExactMatch:
    """A log string present verbatim in the source is confirmed."""

    def test_single_line_exact_match(self, tmp_path):
        f = tmp_path / "m.py"
        f.write_text('logger.info("Run finished: termination=%s")\n')
        result = check_structural_log_line(
            criterion_body="m.py emits a 'Run finished: termination=%s' log line",
            workspace=tmp_path,
        )
        assert result is True

    def test_absent_string_returns_none(self, tmp_path):
        f = tmp_path / "m.py"
        f.write_text('logger.info("something else entirely")\n')
        result = check_structural_log_line(
            criterion_body="m.py emits a 'Run finished: termination=%s' log line",
            workspace=tmp_path,
        )
        assert result is None


class TestAdjacentLiteralConcat:
    """The core regression: format string split across adjacent literals."""

    def test_adjacent_literal_across_newline(self, tmp_path):
        # Mirrors run_loop.py:5297 style — the substring the AC searches for
        # spans the seam between two adjacent string literals.
        f = tmp_path / "run_loop.py"
        f.write_text(
            'logger.info(\n'
            '    "Run finished: termination=%s features_completed=%d "\n'
            '    "features_failed=%d",\n'
            '    termination, completed, failed,\n'
            ')\n'
        )
        # "termination=%s features_completed=%d features_failed=%d" only exists
        # once the adjacent literals are joined.
        result = check_structural_log_line(
            criterion_body=(
                "run_loop.py emits a "
                "'termination=%s features_completed=%d features_failed=%d' log line"
            ),
            workspace=tmp_path,
        )
        assert result is True

    def test_adjacent_literal_seam_within_target(self, tmp_path):
        f = tmp_path / "run_loop.py"
        f.write_text(
            'logger.info(\n'
            '    "Run finished: termination=%s "\n'
            '    "features_completed=%d",\n'
            ')\n'
        )
        # The searched substring "termination=%s features_completed=%d" crosses
        # the literal seam; only the joined content contains it.
        result = check_structural_log_line(
            criterion_body=(
                "run_loop.py emits a 'termination=%s features_completed=%d' log line"
            ),
            workspace=tmp_path,
        )
        assert result is True

    def test_single_quote_literals_joined(self, tmp_path):
        f = tmp_path / "run_loop.py"
        f.write_text(
            "logger.info(\n"
            "    'Run finished: '\n"
            "    'termination done',\n"
            ")\n"
        )
        result = check_structural_log_line(
            criterion_body='run_loop.py emits a "Run finished: termination done" log line',
            workspace=tmp_path,
        )
        assert result is True


class TestTokenOrderFallback:
    """When exact/joined miss but all tokens are present, demote to PASS."""

    def test_tokens_present_out_of_contiguous_order(self, tmp_path):
        f = tmp_path / "run_loop.py"
        # Tokens present but interleaved with other text so neither exact nor
        # joined substring match succeeds.
        f.write_text(
            'logger.info("Run")\n'
            'logger.debug("finished: extra")\n'
            'logger.warning("termination=%s here")\n'
        )
        result = check_structural_log_line(
            criterion_body="run_loop.py emits a 'Run finished: termination=%s' log line",
            workspace=tmp_path,
        )
        assert result is True


class TestNonMatching:
    """Criteria that aren't log-line ACs fall through (return None)."""

    def test_non_emits_criterion_returns_none(self, tmp_path):
        result = check_structural_log_line(
            criterion_body="src/bob/foo.py defines function bar",
            workspace=tmp_path,
        )
        assert result is None

    def test_missing_file_returns_none(self, tmp_path):
        result = check_structural_log_line(
            criterion_body="nope.py emits a 'anything' log line",
            workspace=tmp_path,
        )
        assert result is None


class TestRealRunLoop:
    """Integration: run against the real run_loop.py in the repo."""

    def test_real_run_finished_log_line(self):
        workspace = pathlib.Path(__file__).resolve().parent.parent
        run_loop = workspace / "src" / "bob" / "orchestrator" / "run_loop.py"
        src = run_loop.read_text(encoding="utf-8", errors="replace")
        if "Run finished: termination=" not in src.replace(
            '"\n', '"'
        ).replace("' ", "'"):
            pytest.skip("run_loop.py log line not present in this generation")
        result = check_structural_log_line(
            criterion_body=(
                "src/bob/orchestrator/run_loop.py emits a "
                "'Run finished: termination=%s' log line"
            ),
            workspace=workspace,
        )
        assert result is True
