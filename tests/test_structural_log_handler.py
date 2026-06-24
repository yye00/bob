"""Tests for bob.structural_log_handler.match_log_line_ac.

Verifies the three-tier search algorithm:
1. Exact match in raw file content.
2. Adjacent-literal join (strips ``["']\\s*\\n\\s*["']`` seams).
3. Token-order fallback (all whitespace tokens present in order).

Also verifies error paths (ValueError on bad input types) and boundary cases.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from bob.structural_log_handler import match_log_line_ac


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: pathlib.Path, filename: str, content: str) -> pathlib.Path:
    path = tmp_path / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Pattern matching — returns None when criterion does not match "emits"
# ---------------------------------------------------------------------------

class TestPatternMatch:
    def test_no_emits_keyword_returns_none(self, tmp_path):
        result = match_log_line_ac("run_loop.py defines function foo", tmp_path)
        assert result is None

    def test_empty_criterion_returns_none(self, tmp_path):
        result = match_log_line_ac("", tmp_path)
        assert result is None

    def test_emits_but_no_quoted_string_returns_none(self, tmp_path):
        result = match_log_line_ac("run_loop.py emits a log line", tmp_path)
        assert result is None

    def test_missing_file_returns_none(self, tmp_path):
        result = match_log_line_ac("nonexistent.py emits a 'hello' log line", tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# Tier 1: Exact match
# ---------------------------------------------------------------------------

class TestExactMatch:
    def test_exact_string_in_file_returns_true(self, tmp_path):
        _write(tmp_path, "run_loop.py", 'logger.info("Run finished: termination=%s")\n')
        result = match_log_line_ac(
            "run_loop.py emits a 'Run finished: termination=%s' log line",
            tmp_path,
        )
        assert result is True

    def test_string_absent_returns_none(self, tmp_path):
        _write(tmp_path, "run_loop.py", 'logger.info("Something else")\n')
        result = match_log_line_ac(
            "run_loop.py emits a 'Run finished: termination=%s' log line",
            tmp_path,
        )
        assert result is None

    def test_exact_match_with_subdirectory_path(self, tmp_path):
        _write(
            tmp_path,
            "src/bob/orchestrator/run_loop.py",
            'logger.info("Queue drained")\n',
        )
        result = match_log_line_ac(
            "src/bob/orchestrator/run_loop.py emits a 'Queue drained' log line",
            tmp_path,
        )
        assert result is True

    def test_exact_match_without_a_keyword(self, tmp_path):
        """Pattern allows optional 'a' between emits and the quoted string."""
        _write(tmp_path, "foo.py", 'log.warning("startup failed")\n')
        result = match_log_line_ac(
            "foo.py emits 'startup failed' log line",
            tmp_path,
        )
        assert result is True


# ---------------------------------------------------------------------------
# Tier 2: Adjacent-literal join
# ---------------------------------------------------------------------------

class TestAdjacentLiteralJoin:
    def test_adjacent_literal_concat_across_newline_returns_true(self, tmp_path):
        content = textwrap.dedent("""\
            logger.info(
                "Run finished: termination=%s features_completed=%d "
                "features_failed=%d cost_usd=%.4f"
            )
        """)
        _write(tmp_path, "run_loop.py", content)
        result = match_log_line_ac(
            "run_loop.py emits a 'Run finished: termination=%s features_completed=%d "
            "features_failed=%d cost_usd=%.4f' log line",
            tmp_path,
        )
        assert result is True

    def test_adjacent_literal_with_extra_whitespace_returns_true(self, tmp_path):
        content = textwrap.dedent("""\
            logger.info(
                "Part one "
                "part two"
            )
        """)
        _write(tmp_path, "foo.py", content)
        result = match_log_line_ac(
            "foo.py emits a 'Part one part two' log line",
            tmp_path,
        )
        assert result is True

    def test_three_part_adjacent_literal_returns_true(self, tmp_path):
        content = textwrap.dedent("""\
            logger.info(
                "alpha "
                "beta "
                "gamma"
            )
        """)
        _write(tmp_path, "foo.py", content)
        result = match_log_line_ac(
            "foo.py emits a 'alpha beta gamma' log line",
            tmp_path,
        )
        assert result is True


# ---------------------------------------------------------------------------
# Tier 3: Token-order fallback
# ---------------------------------------------------------------------------

class TestTokenOrderFallback:
    def test_token_order_fallback_returns_true(self, tmp_path):
        """All tokens present but not adjacent → still passes (with warning)."""
        content = textwrap.dedent("""\
            logger.info(
                "termination=%s "
                "something_extra "
                "features_completed=%d"
            )
        """)
        _write(tmp_path, "run_loop.py", content)
        result = match_log_line_ac(
            "run_loop.py emits a 'termination=%s features_completed=%d' log line",
            tmp_path,
        )
        assert result is True


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

class TestErrorPaths:
    def test_none_criterion_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="criterion_body"):
            match_log_line_ac(criterion_body=None, workspace=tmp_path)  # type: ignore[arg-type]

    def test_int_criterion_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="criterion_body"):
            match_log_line_ac(criterion_body=42, workspace=tmp_path)  # type: ignore[arg-type]

    def test_bytes_criterion_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="criterion_body"):
            match_log_line_ac(
                criterion_body=b"foo.py emits a 'x' log line",  # type: ignore[arg-type]
                workspace=tmp_path,
            )

    def test_none_workspace_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="workspace"):
            match_log_line_ac(
                criterion_body="foo.py emits a 'x' log line",
                workspace=None,  # type: ignore[arg-type]
            )

    def test_string_workspace_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="workspace"):
            match_log_line_ac(
                criterion_body="foo.py emits a 'x' log line",
                workspace=str(tmp_path),  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# Integration: import from bob.structural_log_handler
# ---------------------------------------------------------------------------

class TestModuleImport:
    def test_module_importable(self):
        import bob.structural_log_handler  # noqa: F401

    def test_match_log_line_ac_in_all(self):
        from bob import structural_log_handler
        assert "match_log_line_ac" in structural_log_handler.__all__

    def test_function_callable(self, tmp_path):
        """Smoke test: callable with valid args returns bool|None."""
        result = match_log_line_ac("nonexistent.py emits a 'x' log line", tmp_path)
        assert result is None
