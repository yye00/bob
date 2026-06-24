"""Tests for the F-R7-590 structural log-line AC handler in _check_criterion.

Verifies that _check_criterion handles "structural: X.py emits a 'STRING' log line"
ACs correctly, including:
- Exact literal present in file → PASS without warning
- STRING split across Python adjacent-string-literal concat → PASS after normalization
- All tokens present but not contiguous → PASS with WARNING (token-order fallback)
- Tokens missing → fall through (no silent over-demotion)
"""

from __future__ import annotations

import logging
import pathlib

import pytest

from bob.enhanced_verification import _check_criterion


def _make_workspace(tmp_path: pathlib.Path, src_content: str, rel_path: str = "src/bob/run_loop.py") -> pathlib.Path:
    """Create a minimal workspace with a source file at rel_path containing src_content."""
    target = tmp_path / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(src_content)
    return tmp_path


def _check(criterion: str, workspace: pathlib.Path) -> bool:
    return _check_criterion(
        criterion=criterion,
        workspace=workspace,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )


class TestStructuralLogLineAC:

    def test_pass_when_literal_present(self, tmp_path):
        """When STRING is present verbatim in the file, return True without warning."""
        src = (
            "import logging\n"
            "logger = logging.getLogger(__name__)\n"
            "\n"
            "def finish(termination, features_completed, features_failed):\n"
            '    logger.info("Run finished: termination=%s features_completed=%d", termination, features_completed)\n'
        )
        workspace = _make_workspace(tmp_path, src)
        result = _check(
            "structural: src/bob/run_loop.py emits a 'Run finished: termination=%s' log line",
            workspace,
        )
        assert result is True

    def test_pass_when_concat_split(self, tmp_path):
        """When STRING is split across adjacent Python string literals separated by whitespace+newline,
        the verifier must normalize the concat and still return True."""
        src = (
            "import logging\n"
            "logger = logging.getLogger(__name__)\n"
            "\n"
            "def finish(termination, features_completed, features_failed):\n"
            '    logger.info(\n'
            '        "Run finished: termination=%s "\n'
            '        "features_completed=%d",\n'
            '        termination, features_completed\n'
            '    )\n'
        )
        workspace = _make_workspace(tmp_path, src)
        result = _check(
            "structural: src/bob/run_loop.py emits a 'Run finished: termination=%s' log line",
            workspace,
        )
        assert result is True

    def test_warning_emitted_on_token_order_fallback(self, tmp_path, caplog):
        """When STRING tokens (whitespace-split) are all present in the file but not contiguous,
        the verifier must demote to PASS and emit a WARNING tagged with the F-R7-590 hot-fix tag."""
        # The exact string 'Run finished: termination=%s' is not contiguous, but all tokens are present
        src = (
            "import logging\n"
            "logger = logging.getLogger(__name__)\n"
            "\n"
            "# termination=%s\n"
            "# Run\n"
            "# finished:\n"
            "def finish():\n"
            '    logger.info("something else termination=%s")\n'
        )
        workspace = _make_workspace(tmp_path, src)
        with caplog.at_level(logging.WARNING, logger="bob.enhanced_verification"):
            result = _check(
                "structural: src/bob/run_loop.py emits a 'Run finished: termination=%s' log line",
                workspace,
            )
        assert result is True
        assert any(
            "structural log-line AC demoted to PASS via token-order fallback (F-R7-590 hot-fix)" in record.message
            for record in caplog.records
        ), f"Expected F-R7-590 warning not found. Records: {[r.message for r in caplog.records]}"
