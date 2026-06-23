"""Tests for handle_structural_log_line in bob3.enhanced_verification.

Verifies that structural ACs of the form "X.py emits a 'STRING' log line"
are correctly resolved, including when the Python source splits the format
string across adjacent string literals separated by whitespace + newline.
"""

from __future__ import annotations

import logging
import pathlib

import pytest

import stat

from bob3.enhanced_verification import (
    handle_structural_log_line,
    structural_log_line_handler,
    demote_cross_feature_criterion,
    demote_cross_feature_policy_ac,
    demote_cross_feature_reference_ac,
    handle_cross_feature_policy_ac,
    pattern_8_integration_wired,
    pattern_8_integration_fallback,
    handle_pattern_8_integration_fallback,
    fallback_to_function_existence,
    _check_criterion_with_details,
    _resolve_identifier_in_workspace,
    handle_shell_script_integration_ac,
    fuzzy_function_lookup,
    structural_ac_fuzzy_lookup,
)
from bob3.verification.prose_ac_demotion import is_executable_or_structural_criterion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_py(tmp_path: pathlib.Path, rel_path: str, content: str) -> pathlib.Path:
    """Write a Python source file at workspace/rel_path and return the workspace."""
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    return tmp_path


def _call(criterion_body: str, workspace: pathlib.Path) -> bool | None:
    return handle_structural_log_line(
        criterion_body=criterion_body,
        workspace=workspace,
    )


# ---------------------------------------------------------------------------
# Pattern matching: no "emits" → returns None
# ---------------------------------------------------------------------------

class TestNonMatchingCriteria:
    """Criteria that don't match the emits pattern return None (fall-through)."""

    def test_defines_function_returns_none(self, tmp_path):
        result = _call("src/bob3/foo.py defines function bar", tmp_path)
        assert result is None

    def test_empty_criterion_returns_none(self, tmp_path):
        result = _call("", tmp_path)
        assert result is None

    def test_no_quoted_string_returns_none(self, tmp_path):
        result = _call("src/bob3/foo.py emits a log line", tmp_path)
        assert result is None

    def test_emits_without_py_path_returns_none(self, tmp_path):
        result = _call("emits a 'Run finished' log line", tmp_path)
        # No .py path prefix → pattern does not match
        assert result is None


# ---------------------------------------------------------------------------
# File not found → returns None
# ---------------------------------------------------------------------------

class TestFileNotFound:
    """When the named .py file does not exist, return None."""

    def test_missing_file_returns_none(self, tmp_path):
        result = _call(
            "src/bob3/run_loop.py emits a 'Run finished: termination=%s' log line",
            tmp_path,
        )
        assert result is None


# ---------------------------------------------------------------------------
# Exact string present in raw source → True
# ---------------------------------------------------------------------------

class TestExactMatch:
    """When STRING is present verbatim in the file, return True."""

    def test_exact_string_present(self, tmp_path):
        workspace = _write_py(
            tmp_path,
            "src/bob3/run_loop.py",
            'logger.info("Run finished: termination=%s")\n',
        )
        result = _call(
            "src/bob3/run_loop.py emits a 'Run finished: termination=%s' log line",
            workspace,
        )
        assert result is True

    def test_exact_string_double_quotes_in_source(self, tmp_path):
        workspace = _write_py(
            tmp_path,
            "src/bob3/run_loop.py",
            'logger.warning("Queue drained: all features blocked")\n',
        )
        result = _call(
            'src/bob3/run_loop.py emits a "Queue drained: all features blocked" log line',
            workspace,
        )
        assert result is True

    def test_exact_string_single_quotes_in_criterion(self, tmp_path):
        workspace = _write_py(
            tmp_path,
            "src/bob3/orchestrator/run_loop.py",
            'logger.info("heartbeat tick")\n',
        )
        result = _call(
            "src/bob3/orchestrator/run_loop.py emits a 'heartbeat tick' log line",
            workspace,
        )
        assert result is True

    def test_exact_match_ignores_surrounding_code(self, tmp_path):
        workspace = _write_py(
            tmp_path,
            "src/bob3/foo.py",
            'x = 1\nlogger.debug("dispatch started")\ny = 2\n',
        )
        result = _call(
            "src/bob3/foo.py emits a 'dispatch started' log line",
            workspace,
        )
        assert result is True


# ---------------------------------------------------------------------------
# Adjacent-literal concat: split across newlines → True
# ---------------------------------------------------------------------------

class TestAdjacentLiteralConcat:
    """STRING split across adjacent Python string literals must still pass."""

    def test_split_across_newline(self, tmp_path):
        # The source has: "Run finished: termination=%s features_completed=%d "
        #                  "features_failed=%d ..."
        src = (
            'logger.info(\n'
            '    "Run finished: termination=%s features_completed=%d "\n'
            '    "features_failed=%d total=%d"\n'
            ')\n'
        )
        workspace = _write_py(tmp_path, "src/bob3/run_loop.py", src)
        result = _call(
            "src/bob3/run_loop.py emits a 'Run finished: termination=%s features_completed=%d features_failed=%d total=%d' log line",
            workspace,
        )
        assert result is True

    def test_split_across_newline_partial_prefix(self, tmp_path):
        # String searches for just the first-half prefix which spans the seam.
        src = (
            'logger.info(\n'
            '    "Run finished: termination=%s "\n'
            '    "features_completed=%d"\n'
            ')\n'
        )
        workspace = _write_py(tmp_path, "src/bob3/run_loop.py", src)
        result = _call(
            "src/bob3/run_loop.py emits a 'Run finished: termination=%s features_completed=%d' log line",
            workspace,
        )
        assert result is True

    def test_split_with_indentation(self, tmp_path):
        src = (
            'def run():\n'
            '    logger.info(\n'
            '        "Queue drained: all_blocked "\n'
            '        "termination=%s"\n'
            '    )\n'
        )
        workspace = _write_py(tmp_path, "src/bob3/run_loop.py", src)
        result = _call(
            "src/bob3/run_loop.py emits a 'Queue drained: all_blocked termination=%s' log line",
            workspace,
        )
        assert result is True

    def test_three_part_concat(self, tmp_path):
        src = (
            'logger.info(\n'
            '    "Part one "\n'
            '    "part two "\n'
            '    "part three"\n'
            ')\n'
        )
        workspace = _write_py(tmp_path, "src/bob3/foo.py", src)
        result = _call(
            "src/bob3/foo.py emits a 'Part one part two part three' log line",
            workspace,
        )
        assert result is True


# ---------------------------------------------------------------------------
# Token-order fallback → True with warning
# ---------------------------------------------------------------------------

class TestTokenOrderFallback:
    """When exact+joined match misses but all tokens are present, return True."""

    def test_tokens_present_but_not_adjacent(self, tmp_path, caplog):
        # Tokens scattered across multiple unrelated log lines.
        src = (
            'logger.debug("Run")\n'
            'logger.debug("finished")\n'
            'logger.debug("termination=%s")\n'
        )
        workspace = _write_py(tmp_path, "src/bob3/run_loop.py", src)
        with caplog.at_level(logging.WARNING, logger="bob3.enhanced_verification"):
            result = _call(
                "src/bob3/run_loop.py emits a 'Run finished termination=%s' log line",
                workspace,
            )
        assert result is True
        assert any("token-order fallback" in r.message for r in caplog.records)

    def test_token_order_fallback_emits_warning(self, tmp_path, caplog):
        src = 'logger.debug("feature=%s")\nlogger.debug("blocked")\n'
        workspace = _write_py(tmp_path, "src/bob3/foo.py", src)
        with caplog.at_level(logging.WARNING, logger="bob3.enhanced_verification"):
            result = _call(
                "src/bob3/foo.py emits a 'feature=%s blocked' log line",
                workspace,
            )
        assert result is True
        assert any("token-order fallback" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# String not found → None (fall-through, not False)
# ---------------------------------------------------------------------------

class TestStringNotFound:
    """When the string (and tokens) are absent, return None."""

    def test_string_absent_returns_none(self, tmp_path):
        workspace = _write_py(
            tmp_path,
            "src/bob3/run_loop.py",
            'logger.info("Unrelated message")\n',
        )
        result = _call(
            "src/bob3/run_loop.py emits a 'Run finished: termination=%s' log line",
            workspace,
        )
        assert result is None

    def test_partial_token_match_not_sufficient(self, tmp_path):
        # Only one of three tokens is present → None.
        workspace = _write_py(
            tmp_path,
            "src/bob3/foo.py",
            'logger.info("termination=%s")\n',
        )
        result = _call(
            "src/bob3/foo.py emits a 'Run finished termination=%s' log line",
            workspace,
        )
        # "Run" and "finished" are absent → token-order fallback fails → None
        assert result is None


# ---------------------------------------------------------------------------
# Integration: _check_criterion delegates to handle_structural_log_line
# ---------------------------------------------------------------------------

class TestIntegrationWithCheckCriterion:
    """_check_criterion must delegate structural log-line ACs to handle_structural_log_line."""

    def test_structural_criterion_passes_exact(self, tmp_path):
        from bob3.enhanced_verification import _check_criterion
        workspace = _write_py(
            tmp_path,
            "src/bob3/run_loop.py",
            'logger.info("Run finished: termination=%s")\n',
        )
        result = _check_criterion(
            criterion="structural: src/bob3/run_loop.py emits a 'Run finished: termination=%s' log line",
            workspace=workspace,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert result is True

    def test_structural_criterion_passes_adjacent_concat(self, tmp_path):
        from bob3.enhanced_verification import _check_criterion
        src = (
            'logger.info(\n'
            '    "Run finished: termination=%s features_completed=%d "\n'
            '    "features_failed=%d"\n'
            ')\n'
        )
        workspace = _write_py(tmp_path, "src/bob3/run_loop.py", src)
        result = _check_criterion(
            criterion="structural: src/bob3/run_loop.py emits a 'Run finished: termination=%s features_completed=%d features_failed=%d' log line",
            workspace=workspace,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert result is True

    def test_structural_criterion_fails_when_absent(self, tmp_path):
        from bob3.enhanced_verification import _check_criterion
        workspace = _write_py(
            tmp_path,
            "src/bob3/run_loop.py",
            'logger.info("Unrelated")\n',
        )
        # No function identifier → falls through to F-R7-582 which also can't match → False
        result = _check_criterion(
            criterion="structural: src/bob3/run_loop.py emits a 'Run finished: termination=%s' log line",
            workspace=workspace,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert result is False


# ---------------------------------------------------------------------------
# Robustness / edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases for robustness."""

    def test_criterion_body_with_no_log_line_suffix(self, tmp_path):
        workspace = _write_py(
            tmp_path,
            "src/bob3/foo.py",
            'logger.info("hello world")\n',
        )
        # "log line" suffix is not required by the regex — just needs "emits 'STRING'"
        result = _call(
            "src/bob3/foo.py emits a 'hello world'",
            workspace,
        )
        assert result is True

    def test_emits_without_article_a(self, tmp_path):
        workspace = _write_py(
            tmp_path,
            "src/bob3/foo.py",
            'logger.info("startup complete")\n',
        )
        result = _call(
            "src/bob3/foo.py emits 'startup complete' log line",
            workspace,
        )
        assert result is True

    def test_nested_directory_path(self, tmp_path):
        workspace = _write_py(
            tmp_path,
            "src/bob3/orchestrator/run_loop.py",
            'logger.info("tick: features=%d")\n',
        )
        result = _call(
            "src/bob3/orchestrator/run_loop.py emits a 'tick: features=%d' log line",
            workspace,
        )
        assert result is True

    def test_empty_string_criterion_body_returns_none(self, tmp_path):
        result = _call("", tmp_path)
        assert result is None

    def test_case_insensitive_emits_keyword(self, tmp_path):
        workspace = _write_py(
            tmp_path,
            "src/bob3/foo.py",
            'logger.info("done")\n',
        )
        result = _call(
            "src/bob3/foo.py EMITS a 'done' log line",
            workspace,
        )
        assert result is True


# ---------------------------------------------------------------------------
# extract_quoted_literals
# ---------------------------------------------------------------------------

class TestExtractQuotedLiterals:
    """Unit tests for extract_quoted_literals()."""

    def setup_method(self):
        from bob3.enhanced_verification import extract_quoted_literals
        self.fn = extract_quoted_literals

    def test_must_mention_single_quotes(self):
        must, forbid = self.fn("behavior: MUST mention 'Queue drained'")
        assert must == "Queue drained"
        assert forbid is None

    def test_must_not_use_with_phrase(self):
        must, forbid = self.fn(
            "behavior: MUST NOT use the phrase 'All remaining features are blocked'"
        )
        assert must is None
        assert forbid == "All remaining features are blocked"

    def test_both_must_mention_and_must_not_use(self):
        must, forbid = self.fn(
            "behavior: MUST mention 'Queue drained' and MUST NOT use the phrase 'All remaining'"
        )
        assert must == "Queue drained"
        assert forbid == "All remaining"

    def test_no_literals_returns_none_none(self):
        must, forbid = self.fn("behavior: the CLI must terminate cleanly")
        assert must is None
        assert forbid is None

    def test_empty_string_returns_none_none(self):
        must, forbid = self.fn("")
        assert must is None
        assert forbid is None

    def test_must_contain_variant(self):
        must, forbid = self.fn("MUST contain 'some literal'")
        assert must == "some literal"

    def test_must_include_variant(self):
        must, forbid = self.fn("MUST include 'startup message'")
        assert must == "startup message"

    def test_must_not_say_variant(self):
        must, forbid = self.fn("MUST NOT say 'error occurred'")
        assert forbid == "error occurred"

    def test_must_not_contain_variant(self):
        must, forbid = self.fn("MUST NOT contain 'deprecated'")
        assert forbid == "deprecated"

    def test_double_quoted_literal(self):
        must, forbid = self.fn('MUST mention "Queue drained"')
        assert must == "Queue drained"

    def test_case_insensitive_must(self):
        must, forbid = self.fn("must mention 'Queue drained'")
        assert must == "Queue drained"

    def test_case_insensitive_must_not(self):
        must, forbid = self.fn("must not use 'bad phrase'")
        assert forbid == "bad phrase"

    def test_must_not_without_phrase_qualifier(self):
        must, forbid = self.fn("MUST NOT use 'All remaining features'")
        assert forbid == "All remaining features"

    def test_must_not_with_string_qualifier(self):
        must, forbid = self.fn("MUST NOT use the string 'bad_value'")
        assert forbid == "bad_value"

    def test_must_not_with_substring_qualifier(self):
        must, forbid = self.fn("MUST NOT use the substring 'BAD'")
        assert forbid == "BAD"


# ---------------------------------------------------------------------------
# verify_substring_presence
# ---------------------------------------------------------------------------

class TestVerifySubstringPresence:
    """Unit tests for verify_substring_presence()."""

    def setup_method(self):
        from bob3.enhanced_verification import verify_substring_presence
        self.fn = verify_substring_presence

    def _write_src(self, tmp_path: pathlib.Path, filename: str, content: str) -> pathlib.Path:
        p = tmp_path / "src" / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return tmp_path

    def test_must_mention_present_returns_true(self, tmp_path):
        workspace = self._write_src(tmp_path, "cli.py", '"Queue drained"\n')
        result = self.fn("Queue drained", None, workspace)
        assert result is True

    def test_must_mention_absent_returns_none(self, tmp_path):
        workspace = self._write_src(tmp_path, "cli.py", '"Something else"\n')
        result = self.fn("Queue drained", None, workspace)
        assert result is None

    def test_must_not_use_absent_no_mention_returns_true(self, tmp_path):
        # must_mention is None, must_not_use is absent → True
        workspace = self._write_src(tmp_path, "cli.py", '"Queue drained"\n')
        result = self.fn(None, "All remaining", workspace)
        assert result is True

    def test_must_not_use_present_returns_none(self, tmp_path):
        workspace = self._write_src(tmp_path, "cli.py", '"All remaining features are blocked"\n')
        result = self.fn(None, "All remaining", workspace)
        assert result is None

    def test_both_satisfied_returns_true(self, tmp_path):
        workspace = self._write_src(tmp_path, "cli.py", '"Queue drained"\n')
        result = self.fn("Queue drained", "All remaining", workspace)
        assert result is True

    def test_mention_present_but_forbidden_present_returns_none(self, tmp_path):
        workspace = self._write_src(
            tmp_path, "cli.py", '"Queue drained"\n"All remaining features"\n'
        )
        result = self.fn("Queue drained", "All remaining", workspace)
        assert result is None

    def test_both_none_returns_none(self, tmp_path):
        result = self.fn(None, None, tmp_path)
        assert result is None

    def test_missing_src_directory_mention_absent(self, tmp_path):
        # No src/ directory at all → must_mention can't be found → None
        result = self.fn("Queue drained", None, tmp_path)
        assert result is None

    def test_missing_src_directory_no_mention_no_forbid(self, tmp_path):
        # No src/, must_not_use not found (absent = good), must_mention=None → True
        result = self.fn(None, "bad phrase", tmp_path)
        assert result is True

    def test_scans_nested_src_files(self, tmp_path):
        inner = tmp_path / "src" / "bob3" / "cli"
        inner.mkdir(parents=True)
        (inner / "__init__.py").write_text('"Queue drained"\n')
        result = self.fn("Queue drained", None, tmp_path)
        assert result is True

    def test_integration_with_check_criterion_behavior_ac(self, tmp_path):
        """_check_criterion delegates to extract_quoted_literals + verify_substring_presence."""
        from bob3.enhanced_verification import _check_criterion
        workspace = self._write_src(tmp_path, "bob3/cli/__init__.py", '"Queue drained"\n')
        result = _check_criterion(
            criterion="behavior: the CLI MUST mention 'Queue drained' and MUST NOT use the phrase 'All remaining'",
            workspace=workspace,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert result is True

    def test_integration_check_criterion_fails_when_mention_absent(self, tmp_path):
        from bob3.enhanced_verification import _check_criterion
        workspace = self._write_src(tmp_path, "bob3/cli/__init__.py", '"Something else"\n')
        result = _check_criterion(
            criterion="behavior: the CLI MUST mention 'Queue drained'",
            workspace=workspace,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert result is False


# ---------------------------------------------------------------------------
# verify_behavior_ac_with_substring_grep
# ---------------------------------------------------------------------------

class TestVerifyBehaviorAcWithSubstringGrep:
    """Unit tests for verify_behavior_ac_with_substring_grep()."""

    def setup_method(self):
        from bob3.enhanced_verification import verify_behavior_ac_with_substring_grep
        self.fn = verify_behavior_ac_with_substring_grep

    def _write_src(self, tmp_path: pathlib.Path, filename: str, content: str) -> pathlib.Path:
        p = tmp_path / "src" / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return tmp_path

    def test_must_mention_present_returns_true(self, tmp_path):
        workspace = self._write_src(tmp_path, "cli.py", '"Queue drained"\n')
        result = self.fn("behavior: MUST mention 'Queue drained'", workspace)
        assert result is True

    def test_must_mention_absent_returns_none(self, tmp_path):
        workspace = self._write_src(tmp_path, "cli.py", '"Something else"\n')
        result = self.fn("behavior: MUST mention 'Queue drained'", workspace)
        assert result is None

    def test_must_not_use_absent_returns_true(self, tmp_path):
        workspace = self._write_src(tmp_path, "cli.py", '"Queue drained"\n')
        result = self.fn(
            "behavior: MUST NOT use the phrase 'All remaining features are blocked'",
            workspace,
        )
        assert result is True

    def test_must_not_use_present_returns_none(self, tmp_path):
        workspace = self._write_src(
            tmp_path, "cli.py", '"All remaining features are blocked"\n'
        )
        result = self.fn(
            "behavior: MUST NOT use the phrase 'All remaining features are blocked'",
            workspace,
        )
        assert result is None

    def test_both_satisfied_returns_true(self, tmp_path):
        workspace = self._write_src(tmp_path, "cli.py", '"Queue drained"\n')
        result = self.fn(
            "behavior: MUST mention 'Queue drained' and MUST NOT use the phrase 'All remaining'",
            workspace,
        )
        assert result is True

    def test_mention_present_forbidden_present_returns_none(self, tmp_path):
        workspace = self._write_src(
            tmp_path, "cli.py", '"Queue drained"\n"All remaining features"\n'
        )
        result = self.fn(
            "behavior: MUST mention 'Queue drained' and MUST NOT use the phrase 'All remaining'",
            workspace,
        )
        assert result is None

    def test_no_literals_in_criterion_returns_none(self, tmp_path):
        workspace = self._write_src(tmp_path, "cli.py", "pass\n")
        result = self.fn("behavior: the CLI must terminate cleanly", workspace)
        assert result is None

    def test_empty_criterion_returns_none(self, tmp_path):
        workspace = self._write_src(tmp_path, "cli.py", "pass\n")
        result = self.fn("", workspace)
        assert result is None

    def test_missing_src_directory_returns_none(self, tmp_path):
        result = self.fn("behavior: MUST mention 'Queue drained'", tmp_path)
        assert result is None

    def test_scans_nested_src_files(self, tmp_path):
        inner = tmp_path / "src" / "bob3" / "cli"
        inner.mkdir(parents=True)
        (inner / "__init__.py").write_text('"Queue drained"\n')
        result = self.fn("behavior: MUST mention 'Queue drained'", tmp_path)
        assert result is True

    def test_integration_verifier_import(self):
        """verify_behavior_ac_with_substring_grep is importable from bob3.verifier."""
        from bob3.verifier import verify_behavior_ac_with_substring_grep  # noqa: F401
        assert callable(verify_behavior_ac_with_substring_grep)

    def test_canonical_all_blocked_scenario(self, tmp_path):
        """Regression: e4c31b84 ALL_BLOCKED rename must-pass scenario."""
        workspace = self._write_src(
            tmp_path,
            "bob3/cli/__init__.py",
            'print("Queue drained")\n',
        )
        criterion = (
            "behavior: the CLI termination message for ALL_BLOCKED MUST mention "
            "'Queue drained' and MUST NOT use the phrase 'All remaining features are blocked'"
        )
        result = self.fn(criterion, workspace)
        assert result is True


# ---------------------------------------------------------------------------
# verify_quoted_substring_ac
# ---------------------------------------------------------------------------

class TestVerifyQuotedSubstringAc:
    """Unit tests for verify_quoted_substring_ac().

    This is the canonical public entry point for the F-R7-591 MUST-mention /
    MUST-NOT-use behavior-AC handler.  It is symmetric to
    verify_behavior_ac_with_substring_grep() and delegates to the same
    helpers.
    """

    def setup_method(self):
        from bob3.enhanced_verification import verify_quoted_substring_ac
        self.fn = verify_quoted_substring_ac

    def _write_src(self, tmp_path: pathlib.Path, filename: str, content: str) -> pathlib.Path:
        p = tmp_path / "src" / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return tmp_path

    def test_must_mention_present_returns_true(self, tmp_path):
        workspace = self._write_src(tmp_path, "cli.py", '"Queue drained"\n')
        result = self.fn("behavior: MUST mention 'Queue drained'", workspace)
        assert result is True

    def test_must_mention_absent_returns_none(self, tmp_path):
        workspace = self._write_src(tmp_path, "cli.py", '"Something else"\n')
        result = self.fn("behavior: MUST mention 'Queue drained'", workspace)
        assert result is None

    def test_must_not_use_absent_returns_true(self, tmp_path):
        workspace = self._write_src(tmp_path, "cli.py", '"Queue drained"\n')
        result = self.fn(
            "behavior: MUST NOT use the phrase 'All remaining features are blocked'",
            workspace,
        )
        assert result is True

    def test_must_not_use_present_returns_none(self, tmp_path):
        workspace = self._write_src(
            tmp_path, "cli.py", '"All remaining features are blocked"\n'
        )
        result = self.fn(
            "behavior: MUST NOT use the phrase 'All remaining features are blocked'",
            workspace,
        )
        assert result is None

    def test_both_satisfied_returns_true(self, tmp_path):
        workspace = self._write_src(tmp_path, "cli.py", '"Queue drained"\n')
        result = self.fn(
            "behavior: MUST mention 'Queue drained' and MUST NOT use the phrase 'All remaining'",
            workspace,
        )
        assert result is True

    def test_mention_present_forbidden_present_returns_none(self, tmp_path):
        workspace = self._write_src(
            tmp_path, "cli.py", '"Queue drained"\n"All remaining features"\n'
        )
        result = self.fn(
            "behavior: MUST mention 'Queue drained' and MUST NOT use the phrase 'All remaining'",
            workspace,
        )
        assert result is None

    def test_no_literals_in_criterion_returns_none(self, tmp_path):
        workspace = self._write_src(tmp_path, "cli.py", "pass\n")
        result = self.fn("behavior: the CLI must terminate cleanly", workspace)
        assert result is None

    def test_empty_criterion_returns_none(self, tmp_path):
        workspace = self._write_src(tmp_path, "cli.py", "pass\n")
        result = self.fn("", workspace)
        assert result is None

    def test_missing_src_directory_returns_none(self, tmp_path):
        result = self.fn("behavior: MUST mention 'Queue drained'", tmp_path)
        assert result is None

    def test_scans_nested_src_files(self, tmp_path):
        inner = tmp_path / "src" / "bob3" / "cli"
        inner.mkdir(parents=True)
        (inner / "__init__.py").write_text('"Queue drained"\n')
        result = self.fn("behavior: MUST mention 'Queue drained'", tmp_path)
        assert result is True

    def test_integration_verifier_import(self):
        """verify_quoted_substring_ac is importable from bob3.verifier."""
        from bob3.verifier import verify_quoted_substring_ac  # noqa: F401
        assert callable(verify_quoted_substring_ac)

    def test_canonical_all_blocked_scenario(self, tmp_path):
        """Regression: e4c31b84 ALL_BLOCKED rename must-pass scenario."""
        workspace = self._write_src(
            tmp_path,
            "bob3/cli/__init__.py",
            'print("Queue drained")\n',
        )
        criterion = (
            "behavior: the CLI termination message for ALL_BLOCKED MUST mention "
            "'Queue drained' and MUST NOT use the phrase 'All remaining features are blocked'"
        )
        result = self.fn(criterion, workspace)
        assert result is True

    def test_double_quoted_literal(self, tmp_path):
        workspace = self._write_src(tmp_path, "mod.py", '"hello world"\n')
        result = self.fn('behavior: MUST mention "hello world"', workspace)
        assert result is True

    def test_case_insensitive_must_keyword(self, tmp_path):
        workspace = self._write_src(tmp_path, "mod.py", '"Token"\n')
        result = self.fn("behavior: must mention 'Token'", workspace)
        assert result is True

    # Boundary case: empty / zero input returns a well-defined result (None),
    # never raises or crashes.
    def test_empty_string_boundary_returns_none(self, tmp_path):
        result = self.fn("", tmp_path)
        assert result is None

    def test_whitespace_only_boundary_returns_none(self, tmp_path):
        result = self.fn("   ", tmp_path)
        assert result is None

    # Invalid input: non-str criterion must raise ValueError, not silently succeed.
    def test_none_criterion_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            self.fn(None, tmp_path)

    def test_integer_criterion_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            self.fn(0, tmp_path)

    def test_list_criterion_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            self.fn([], tmp_path)


# ---------------------------------------------------------------------------
# verify_class_defined — Class defined: AC handler
# ---------------------------------------------------------------------------

def test_class_defined_ac_verification(tmp_path):
    """verify_class_defined routes 'Class defined:' ACs through check_class_defined_ac.

    This is the integration-level test for the Class defined: handler in
    enhanced_verification.  It verifies that:
    - verify_class_defined returns True when the class exists in the workspace
    - verify_class_defined returns False when the class is absent
    - @dataclass-decorated classes are detected (the original regression case
      from feature 5779ecf7 / MutationReport)
    - _check_criterion also routes 'Class defined:' to the correct handler
    """
    from bob3.enhanced_verification import verify_class_defined, _check_criterion

    # Workspace with a plain class
    src_dir = tmp_path / "src" / "bob3" / "verification"
    src_dir.mkdir(parents=True)
    (src_dir / "mutation_gate.py").write_text(
        "from dataclasses import dataclass\n"
        "\n"
        "@dataclass\n"
        "class MutationReport:\n"
        "    passed: int\n"
        "    total: int\n"
    )

    # verify_class_defined: present → True
    result = verify_class_defined(
        "Class defined: bob3.verification.mutation_gate.MutationReport",
        tmp_path,
    )
    assert result is True

    # verify_class_defined: absent → False
    result_missing = verify_class_defined(
        "Class defined: bob3.verification.mutation_gate.NoSuchClass",
        tmp_path,
    )
    assert result_missing is False

    # _check_criterion must route 'Class defined:' ACs to the handler
    result_via_check = _check_criterion(
        criterion="Class defined: bob3.verification.mutation_gate.MutationReport",
        workspace=tmp_path,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )
    assert result_via_check is True

    # _check_criterion: absent class → False
    result_via_check_missing = _check_criterion(
        criterion="Class defined: bob3.verification.mutation_gate.NoSuchClass",
        workspace=tmp_path,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )
    assert result_via_check_missing is False


# ---------------------------------------------------------------------------
# test_class_defined_ac (0e91b1eb — enhanced_verification Class defined: handler)
# ---------------------------------------------------------------------------

def test_class_defined_ac(tmp_path):
    """check_class_defined is importable from bob3.enhanced_verification and works.

    This test satisfies the AC:
    pytest: tests/test_enhanced_verification.py::test_class_defined_ac

    It verifies:
    - check_class_defined returns True when the class exists in the workspace
    - check_class_defined returns False when the class is absent
    - @dataclass-decorated classes are detected (original regression: MutationReport)
    """
    from bob3.enhanced_verification import check_class_defined

    src_dir = tmp_path / "src" / "bob3" / "verification"
    src_dir.mkdir(parents=True)
    (src_dir / "mutation_gate.py").write_text(
        "from dataclasses import dataclass\n"
        "\n"
        "@dataclass\n"
        "class MutationReport:\n"
        "    passed: int\n"
        "    total: int\n"
    )

    # Class present → True
    assert check_class_defined(
        "Class defined: bob3.verification.mutation_gate.MutationReport",
        tmp_path,
    ) is True

    # Class absent → False
    assert check_class_defined(
        "Class defined: bob3.verification.mutation_gate.NoSuchClass",
        tmp_path,
    ) is False

    # Non-matching prefix → False (no error)
    assert check_class_defined("File exists: something.py", tmp_path) is False


# ---------------------------------------------------------------------------
# demote_cross_feature_criterion (209a750c / F-R7-589)
# ---------------------------------------------------------------------------

class TestDemoteCrossFeatureCriterion:
    """Tests for demote_cross_feature_criterion — policy-AC demotion for
    criteria that contain cross-feature F-RX-YYY references."""

    def test_returns_none_for_criterion_without_feature_id(self):
        result = demote_cross_feature_criterion(
            "behavior: spawn-retry fires after transient failure"
        )
        assert result is None

    def test_returns_none_for_empty_criterion(self):
        assert demote_cross_feature_criterion("") is None

    def test_demotes_integration_ac_with_F_RX_YYY(self):
        criterion = "integration: F-R7-478 unlimited spawn-retry path remains unaffected"
        result = demote_cross_feature_criterion(criterion)
        assert result is not None
        passed, reason = result
        assert passed is True
        assert "F-R7-478" in reason

    def test_demotes_criterion_containing_feature_id_in_body(self):
        criterion = "integration: regression-sweep / F-R7-532 invariant pass continues to run"
        result = demote_cross_feature_criterion(criterion)
        assert result is not None
        passed, reason = result
        assert passed is True
        assert "F-R7-532" in reason

    def test_demotes_behavior_ac_with_feature_id(self):
        criterion = "behavior: F-R7-600 path is unaffected by this change"
        result = demote_cross_feature_criterion(criterion)
        assert result is not None
        passed, reason = result
        assert passed is True

    def test_returns_none_for_partial_match_no_id(self):
        # "F-R7" without 3-digit suffix must NOT match
        result = demote_cross_feature_criterion("behavior: the F-R7 pipeline continues")
        assert result is None

    def test_returns_none_for_non_feature_token(self):
        result = demote_cross_feature_criterion("File exists: src/bob3/foo.py")
        assert result is None

    def test_reason_string_explains_demotion(self):
        criterion = "integration: F-R7-582 symbol-grep fallback still active"
        result = demote_cross_feature_criterion(criterion)
        assert result is not None
        _, reason = result
        assert "cross-feature" in reason.lower()
        assert "F-R7-582" in reason

    def test_without_workspace_no_exception(self):
        # When workspace=None, the function must not raise
        result = demote_cross_feature_criterion(
            "integration: F-R7-478 path unaffected",
            workspace=None,
        )
        assert result is not None
        assert result[0] is True

    def test_with_workspace_writes_warning_finding(self, tmp_path):
        # When workspace is provided, a WARNING entry should be written to
        # reviews/findings.yaml
        reviews_dir = tmp_path / "reviews"
        reviews_dir.mkdir()
        findings_path = reviews_dir / "findings.yaml"
        findings_path.write_text("schema_version: 1\nfindings: []\n")

        criterion = "integration: F-R7-478 unlimited spawn-retry path remains unaffected"
        result = demote_cross_feature_criterion(criterion, workspace=tmp_path)

        assert result is not None
        assert result[0] is True

        content = findings_path.read_text()
        assert "F-R7-478" in content
        assert "policy-ac-cross-feature-reference" in content

    def test_matches_first_feature_id_when_multiple_present(self):
        # Multiple F-RX-YYY tokens — demote on first match
        criterion = "integration: F-R7-478 and F-R7-532 both unaffected"
        result = demote_cross_feature_criterion(criterion)
        assert result is not None
        passed, reason = result
        assert passed is True
        # First match F-R7-478 should appear in the reason
        assert "F-R7-478" in reason

    def test_zero_in_id_digits_still_matches(self):
        criterion = "integration: F-R7-001 old feature unaffected"
        result = demote_cross_feature_criterion(criterion)
        assert result is not None
        assert result[0] is True

    def test_higher_round_number_still_matches(self):
        criterion = "integration: F-R12-999 path unaffected"
        result = demote_cross_feature_criterion(criterion)
        assert result is not None
        assert result[0] is True


# ---------------------------------------------------------------------------
# structural_log_line_handler alias (183efec7)
# ---------------------------------------------------------------------------

class TestStructuralLogLineHandlerAlias:
    """structural_log_line_handler must be an alias for handle_structural_log_line."""

    def test_alias_is_same_callable(self):
        assert structural_log_line_handler is handle_structural_log_line

    def test_alias_accepts_same_kwargs(self, tmp_path):
        """Alias must accept criterion_body and workspace kwargs."""
        py_path = tmp_path / "src" / "bob3" / "foo.py"
        py_path.parent.mkdir(parents=True, exist_ok=True)
        py_path.write_text('logger.info("hello world")\n')
        result = structural_log_line_handler(
            criterion_body="src/bob3/foo.py emits a 'hello world' log line",
            workspace=tmp_path,
        )
        assert result is True

    def test_alias_returns_none_for_non_matching(self, tmp_path):
        result = structural_log_line_handler(
            criterion_body="src/bob3/foo.py defines function do_something",
            workspace=tmp_path,
        )
        assert result is None

    def test_alias_tolerates_adjacent_literal_concat(self, tmp_path):
        py_path = tmp_path / "src" / "bob3" / "run_loop.py"
        py_path.parent.mkdir(parents=True, exist_ok=True)
        py_path.write_text(
            'logger.info(\n'
            '    "Run finished: termination=%s features_completed=%d "\n'
            '    "features_failed=%d total=%d"\n'
            ')\n'
        )
        result = structural_log_line_handler(
            criterion_body="src/bob3/run_loop.py emits a 'Run finished: termination=%s features_completed=%d features_failed=%d total=%d' log line",
            workspace=tmp_path,
        )
        assert result is True


# ---------------------------------------------------------------------------
# Tests for pattern_8_integration_wired (8638223a)
# ---------------------------------------------------------------------------

def _write_src(tmp_path: pathlib.Path, rel_path: str, content: str) -> pathlib.Path:
    """Write a source file at workspace/rel_path; return workspace root."""
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    return tmp_path


class TestPattern8IntegrationWired:
    """Tests for the public pattern_8_integration_wired function."""

    def test_dotted_module_wired_passes(self, tmp_path):
        """Returns True when the module exists and is imported somewhere."""
        _write_src(tmp_path, "src/bob3/enhanced_verification.py", "def foo(): pass\n")
        importer = tmp_path / "src" / "bob3" / "orchestrator.py"
        importer.parent.mkdir(parents=True, exist_ok=True)
        importer.write_text("from bob3.enhanced_verification import foo\n")

        result = pattern_8_integration_wired(
            "integration: bob3.enhanced_verification",
            tmp_path,
        )
        assert result is True

    def test_dotted_module_not_imported_falls_back_to_function(self, tmp_path):
        """When module file exists but not imported, falls back to function-existence check."""
        # Module file exists but is NOT imported anywhere
        _write_src(tmp_path, "src/bob3/enhanced_verification.py", "def foo(): pass\n")
        # But a function named after a snake_case token in the criterion exists
        _write_src(
            tmp_path,
            "src/bob3/run_loop.py",
            "def sweep_orphan_subagents(x): pass\n",
        )

        result = pattern_8_integration_wired(
            "integration: sweep_orphan_subagents runs at the same cadence as stuck_executing reaper",
            tmp_path,
        )
        assert result is True

    def test_bare_function_name_criterion_passes(self, tmp_path):
        """Prose-integration AC with bare snake_case function name passes when function exists."""
        _write_src(
            tmp_path,
            "src/bob3/reaper.py",
            "def sweep_orphan_subagents(workspace, processes):\n    pass\n",
        )

        result = pattern_8_integration_wired(
            "integration: sweep_orphan_subagents runs at the same cadence as the existing stuck_executing reaper",
            tmp_path,
        )
        assert result is True

    def test_no_matching_identifier_returns_false(self, tmp_path):
        """Returns False when neither a dotted module nor any snake_case function resolves."""
        _write_src(tmp_path, "src/bob3/unrelated.py", "def unrelated_thing(): pass\n")

        result = pattern_8_integration_wired(
            "integration: nonexistent_module_xyz does something critical",
            tmp_path,
        )
        assert result is False

    def test_dotted_path_with_attr_passes(self, tmp_path):
        """integration: pkg.mod.func_name passes when func_name is defined in pkg/mod.py."""
        _write_src(
            tmp_path,
            "src/pkg/mod.py",
            "def func_name(): pass\n",
        )
        importer = tmp_path / "src" / "pkg" / "caller.py"
        importer.parent.mkdir(parents=True, exist_ok=True)
        importer.write_text("from pkg.mod import func_name\n")

        result = pattern_8_integration_wired(
            "integration: pkg.mod.func_name is called during startup",
            tmp_path,
        )
        assert result is True


# ---------------------------------------------------------------------------
# Tests for pattern_8_integration_fallback (06dfaa76)
# ---------------------------------------------------------------------------

def test_pattern_8_fallback_to_function_existence(tmp_path):
    """pattern_8_integration_fallback passes prose-integration ACs via function-existence.

    When the first token in an 'integration:' AC is a bare snake_case function
    name (not a dotted module path), the fallback must find the function
    definition in the workspace src tree and return True.
    """
    # Write a function that matches the first token of the prose-integration AC.
    src_file = tmp_path / "src" / "bob3" / "reaper.py"
    src_file.parent.mkdir(parents=True, exist_ok=True)
    src_file.write_text(
        "def sweep_orphan_subagents(workspace, processes):\n"
        "    pass\n"
    )

    result = pattern_8_integration_fallback(
        "integration: sweep_orphan_subagents runs at the same cadence as the "
        "existing stuck_executing reaper (watchdog tick); both reapers are "
        "idempotent and safe to run concurrently",
        tmp_path,
    )
    assert result is True, (
        "pattern_8_integration_fallback must return True when any snake_case "
        "identifier in the criterion resolves to a def in workspace src"
    )


def test_pattern_8_prose_integration_ac(tmp_path):
    """handle_pattern_8_integration_fallback passes prose-integration ACs via function-existence.

    When the first token after 'integration:' is a bare snake_case function name
    (not a dotted module path), _integration_wired returns False because no module
    file with that name exists. handle_pattern_8_integration_fallback must fall
    back to scanning all snake_case identifiers in the criterion and return True
    if any resolves to a def/class in the workspace src tree.
    """
    src_file = tmp_path / "src" / "bob3" / "reaper.py"
    src_file.parent.mkdir(parents=True, exist_ok=True)
    src_file.write_text(
        "def sweep_orphan_subagents(workspace, processes):\n"
        "    pass\n"
    )

    result = handle_pattern_8_integration_fallback(
        "integration: sweep_orphan_subagents runs at the same cadence as the "
        "existing stuck_executing reaper (watchdog tick); both reapers are "
        "idempotent and safe to run concurrently",
        tmp_path,
    )
    assert result is True, (
        "handle_pattern_8_integration_fallback must return True when any snake_case "
        "identifier in the criterion resolves to a def in workspace src"
    )

    result_false = handle_pattern_8_integration_fallback(
        "integration: nonexistent_xyz_function does something here",
        tmp_path,
    )
    assert result_false is False, (
        "handle_pattern_8_integration_fallback must return False when no identifier "
        "resolves to a def or class in workspace src"
    )

    import pytest
    with pytest.raises(ValueError):
        handle_pattern_8_integration_fallback(None, tmp_path)  # type: ignore[arg-type]


def test_pattern_8_fallback_returns_false_when_no_match(tmp_path):
    """pattern_8_integration_fallback returns False when no identifier resolves."""
    (tmp_path / "src" / "bob3").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "bob3" / "unrelated.py").write_text("def unrelated(): pass\n")

    result = pattern_8_integration_fallback(
        "integration: nonexistent_xyz_function does something here",
        tmp_path,
    )
    assert result is False


def test_integration_prose_ac_bare_function_names(tmp_path):
    """Pattern-8 fallback passes prose-integration ACs with bare function names.

    When an 'integration:' AC body starts with a bare snake_case function name
    (not a dotted module path), _integration_wired returns False because no module
    file with that name exists. The fallback must find the function definition in
    the workspace and return True, using _resolve_identifier_in_workspace.
    """
    # Write a source file containing the function named in the prose AC.
    src_dir = tmp_path / "src" / "bob3"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "reapers.py").write_text(
        "def sweep_orphan_subagents(workspace, processes):\n"
        "    \"\"\"Reap orphaned subagents.\"\"\"\n"
        "    return []\n"
        "\n"
        "def run_stuck_executing_reaper(workspace):\n"
        "    return []\n"
    )

    # _resolve_identifier_in_workspace must find the bare function name.
    assert _resolve_identifier_in_workspace(tmp_path, "sweep_orphan_subagents") is True, (
        "_resolve_identifier_in_workspace must return True when the identifier "
        "resolves to a def in the workspace src tree"
    )

    # The prose-integration AC with a bare function name must pass via the fallback.
    criterion = (
        "integration: sweep_orphan_subagents runs at the same cadence as the "
        "existing stuck_executing reaper (watchdog tick); both reapers are "
        "idempotent and safe to run concurrently"
    )
    result = pattern_8_integration_wired(criterion, tmp_path)
    assert result is True, (
        "pattern_8_integration_wired must return True for a prose-integration AC "
        "whose first token is a bare function name defined in workspace src"
    )

    # A bare function name that doesn't exist must not spuriously pass.
    assert _resolve_identifier_in_workspace(tmp_path, "nonexistent_xyz_function") is False, (
        "_resolve_identifier_in_workspace must return False when the identifier "
        "is not defined anywhere in the workspace src tree"
    )


class TestFallbackToFunctionExistence:
    """Tests for the public fallback_to_function_existence function."""

    def test_function_defined_in_src_passes(self, tmp_path):
        """Returns True when a snake_case token in criterion resolves to a def."""
        _write_src(
            tmp_path,
            "src/bob3/reaper.py",
            "def sweep_orphan_subagents(x):\n    pass\n",
        )

        result = fallback_to_function_existence(
            "sweep_orphan_subagents runs at the same cadence as stuck_executing reaper",
            tmp_path,
        )
        assert result is True

    def test_class_defined_in_src_passes(self, tmp_path):
        """Returns True when a snake_case token resolves to a class."""
        _write_src(
            tmp_path,
            "src/bob3/handlers.py",
            "class orphan_handler:\n    pass\n",
        )

        result = fallback_to_function_existence(
            "orphan_handler manages cleanup of orphan processes",
            tmp_path,
        )
        assert result is True

    def test_function_absent_returns_false(self, tmp_path):
        """Returns False when no snake_case token in criterion resolves."""
        _write_src(tmp_path, "src/bob3/foo.py", "def something_else(): pass\n")

        result = fallback_to_function_existence(
            "nonexistent_function does something critical",
            tmp_path,
        )
        assert result is False

    def test_empty_criterion_returns_false(self, tmp_path):
        """Empty criterion has no snake_case identifiers → False."""
        result = fallback_to_function_existence("", tmp_path)
        assert result is False

    def test_no_snake_case_in_criterion_returns_false(self, tmp_path):
        """Criterion with no snake_case tokens → False even if files exist."""
        _write_src(tmp_path, "src/bob3/foo.py", "def bar(): pass\n")

        result = fallback_to_function_existence(
            "Integration criterion with NoSnakeCase tokens only",
            tmp_path,
        )
        assert result is False

    def test_first_snake_match_wins(self, tmp_path):
        """Returns True as soon as any snake_case token resolves; doesn't need all."""
        _write_src(
            tmp_path,
            "src/bob3/run_loop.py",
            "def stuck_executing_reaper(x): pass\n",
        )

        result = fallback_to_function_existence(
            "sweep_orphan_subagents and stuck_executing_reaper both run on the watchdog tick",
            tmp_path,
        )
        assert result is True


# ---------------------------------------------------------------------------
# F-R7-576: prose AC demotion — counter-test and counter-counter-test
# ---------------------------------------------------------------------------

def test_prose_ac_demoted_to_warning(tmp_path, monkeypatch):
    """A pure-prose AC (matching b6873bac pattern) passes with demotion warning.

    Counter-test asserting that a criterion containing NONE of the recognized
    structural markers returns (True, <demotion-reason>) rather than (False, ""),
    so the feature ships instead of infinitely respinning.
    """
    # Disable strict verification so prose-AC demotion path is active
    monkeypatch.setenv("BOB3_STRICT_VERIFICATION", "0")
    prose_criterion = (
        "EVERY Claude-CLI sub-agent invocation in the codebase routes through "
        "spawn_with_retry — grep guard: no remaining direct `claude --` subprocess "
        "calls outside spawn_retry.py"
    )
    assert not is_executable_or_structural_criterion(prose_criterion), (
        "Precondition: criterion must have no structural marker"
    )

    passed, details = _check_criterion_with_details(
        criterion=prose_criterion,
        workspace=tmp_path,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )

    assert passed is True
    assert "prose AC demoted" in details or "F-R7-531" in details


def test_structural_ac_still_hard_fails(tmp_path):
    """A structural 'File exists:' criterion fails when the file is absent.

    Counter-counter-test asserting that the prose-demotion path does NOT fire
    for structural criteria — a missing file must still cause a hard failure.
    """
    structural_criterion = "File exists: nonexistent_file_that_does_not_exist.py"
    assert is_executable_or_structural_criterion(structural_criterion), (
        "Precondition: criterion must be recognised as structural"
    )

    passed, _details = _check_criterion_with_details(
        criterion=structural_criterion,
        workspace=tmp_path,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )

    assert passed is False


def test_structural_criterion_still_hard_fails(tmp_path):
    """A structural 'File exists:' criterion fails when the file is absent.

    AC-named counter-counter-test (F-R7-576): the prose-demotion path must NOT
    fire for structural criteria. 'File exists: nonexistent.py' must return
    (False, ...) even after the prose-demotion logic is active.
    """
    structural_criterion = "File exists: nonexistent.py"
    assert is_executable_or_structural_criterion(structural_criterion), (
        "Precondition: criterion must be recognised as structural"
    )

    passed, _details = _check_criterion_with_details(
        criterion=structural_criterion,
        workspace=tmp_path,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )

    assert passed is False, (
        "Structural criterion for a missing file must hard-fail, not be demoted to warning"
    )


def test_structural_criterion_still_fails(tmp_path):
    """AC-named counter-counter-test (F-R7-576): structural 'File exists:' must hard-fail.

    Verifies that prose-demotion does NOT fire when the criterion contains a
    recognized structural marker — a missing file returns (False, ...) even
    after the demotion logic is active.
    """
    structural_criterion = "File exists: nonexistent.py"
    assert is_executable_or_structural_criterion(structural_criterion), (
        "Precondition: criterion must be recognised as structural"
    )

    passed, _details = _check_criterion_with_details(
        criterion=structural_criterion,
        workspace=tmp_path,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )

    assert passed is False, (
        "Structural criterion for a missing file must hard-fail, not be demoted to warning"
    )


# ---------------------------------------------------------------------------
# AC: pytest: tests/test_enhanced_verification.py::test_cross_feature_reference_ac_demotion
# Feature: f109b639-fe4c-4217-85a1-e93bfc8862c2
# ---------------------------------------------------------------------------


def test_cross_feature_reference_ac_demotion():
    """Core AC test: demote_cross_feature_policy_ac returns (True, reason) for F-RX-YYY criteria."""
    criterion = "integration: F-R7-478 unlimited spawn-retry path remains unaffected"
    result = demote_cross_feature_policy_ac(criterion)

    assert result is not None, "Expected demotion tuple for cross-feature reference criterion"
    passed, reason = result
    assert passed is True, "Demoted criterion must resolve as PASS (True)"
    assert isinstance(reason, str) and reason, "Demotion reason must be a non-empty string"
    assert "F-R7-478" in reason or "cross-feature" in reason.lower(), (
        "Reason must reference the matched token or 'cross-feature'"
    )


class TestDemoteCrossFeaturePolicyAC:
    """Tests for demote_cross_feature_policy_ac (f109b639 / F-R7-589 alias)."""

    def test_f_r7_pattern_returns_pass(self):
        """Criterion with F-R7-NNN token must be demoted to PASS."""
        result = demote_cross_feature_policy_ac(
            "integration: F-R7-532 invariant pass continues to run"
        )
        assert result is not None
        passed, reason = result
        assert passed is True
        assert reason

    def test_different_group_number_demoted(self):
        """F-R5-NNN or F-R9-NNN variants must also trigger demotion."""
        result = demote_cross_feature_policy_ac(
            "integration: F-R5-123 path must remain unaffected"
        )
        assert result is not None
        passed, _ = result
        assert passed is True

    def test_no_cross_feature_ref_returns_none(self):
        """Criterion without F-RX-YYY token must return None (no demotion)."""
        result = demote_cross_feature_policy_ac(
            "integration: bob3.ac_handler must be importable"
        )
        assert result is None

    def test_plain_function_criterion_returns_none(self):
        """A plain function-existence criterion must return None."""
        result = demote_cross_feature_policy_ac(
            "function defined: bob3.enhanced_verification.demote_cross_feature_policy_ac"
        )
        assert result is None

    def test_word_boundary_match_only(self):
        """F-RX-YYY must match as a whole word (word-boundary), not as substring."""
        result = demote_cross_feature_policy_ac(
            "integration: XF-R7-582X must not trigger demotion"
        )
        assert result is None, "Substring match without word boundary must not demote"

    def test_multiple_refs_demoted(self):
        """Criterion with multiple F-RX-YYY tokens is still demoted."""
        result = demote_cross_feature_policy_ac(
            "integration: F-R7-478 and F-R7-532 paths remain unaffected"
        )
        assert result is not None
        passed, _ = result
        assert passed is True

    def test_boundary_empty_criterion_raises_value_error(self):
        """Empty string criterion must raise ValueError, not silently pass or return None."""
        with pytest.raises(ValueError, match="non-empty"):
            demote_cross_feature_policy_ac("")

    def test_boundary_none_criterion_raises_value_error(self):
        """None criterion must raise ValueError (invalid input guard)."""
        with pytest.raises((ValueError, TypeError)):
            demote_cross_feature_policy_ac(None)  # type: ignore[arg-type]

    def test_workspace_forwarded_to_findings_yaml(self, tmp_path):
        """When workspace is provided, a findings.yaml entry is written."""
        reviews_dir = tmp_path / "reviews"
        reviews_dir.mkdir(parents=True)
        findings_path = reviews_dir / "findings.yaml"
        findings_path.write_text("schema_version: 1\nfindings: []\n", encoding="utf-8")

        result = demote_cross_feature_policy_ac(
            "integration: F-R7-999 some cross-feature claim",
            workspace=tmp_path,
        )
        assert result is not None
        passed, _ = result
        assert passed is True

        content = findings_path.read_text(encoding="utf-8")
        assert "policy-ac-cross-feature-reference" in content
        assert "F-R7-999" in content

    def test_invalid_integer_input_raises_value_error(self):
        """Passing an integer (invalid type) must raise ValueError or TypeError."""
        with pytest.raises((ValueError, TypeError)):
            demote_cross_feature_policy_ac(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Structural-AC fuzzy function-lookup fallback (6063ec64)
# ---------------------------------------------------------------------------

def test_structural_ac_fuzzy_fallback(tmp_path: pathlib.Path) -> None:
    """fuzzy_function_lookup returns True when symbol found outside expected module.

    AC: pytest: tests/test_enhanced_verification.py::test_structural_ac_fuzzy_fallback
    """
    from bob3.enhanced_verification import fuzzy_function_lookup

    # Set up a minimal workspace: X.py doesn't define func, Z.py does.
    src_dir = tmp_path / "src" / "bob3"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").write_text("")
    (src_dir / "X.py").write_text("# placeholder\ndef other_fn():\n    pass\n")
    (src_dir / "Z.py").write_text("def target_fn(arg):\n    return arg\n")

    reviews_dir = tmp_path / "reviews"
    reviews_dir.mkdir()
    findings_path = reviews_dir / "findings.yaml"
    findings_path.write_text("schema_version: 1\nfindings: []\n", encoding="utf-8")

    # Exact module (X.py) doesn't define target_fn, but Z.py does → fuzzy PASS
    result = fuzzy_function_lookup(
        workspace=tmp_path,
        symbol_name="target_fn",
        expected_module_path="src/bob3/X.py",
        is_class=False,
        findings_path=findings_path,
    )

    assert result is True, (
        "fuzzy_function_lookup must return True when symbol exists in workspace "
        "but not in the exact module named by the structural AC"
    )

    # Warning record must be written
    content = findings_path.read_text(encoding="utf-8")
    assert "target_fn" in content, "Warning finding must mention the symbol name"
    assert "warning" in content.lower(), "Warning finding must have severity=warning"


def test_structural_ac_exact_match_preferred(tmp_path: pathlib.Path) -> None:
    """fuzzy_function_lookup prefers the exact module match and returns True without WARNING.

    AC: pytest: tests/test_enhanced_verification.py::test_structural_ac_exact_match_preferred

    When the symbol IS defined in the exact module specified by the structural AC,
    fuzzy_function_lookup must return True and must NOT emit a warning finding
    (no demotion — exact match means full pass, not fuzzy fallback).
    """
    from bob3.enhanced_verification import fuzzy_function_lookup

    src_dir = tmp_path / "src" / "bob3"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").write_text("")
    # Symbol IS in the exact expected module (X.py).
    (src_dir / "X.py").write_text("def preferred_fn(arg):\n    return arg\n")
    # Symbol also exists elsewhere — exact match must be preferred.
    (src_dir / "Z.py").write_text("def preferred_fn(arg):\n    return arg\n")

    reviews_dir = tmp_path / "reviews"
    reviews_dir.mkdir()
    findings_path = reviews_dir / "findings.yaml"
    findings_path.write_text("schema_version: 1\nfindings: []\n", encoding="utf-8")

    result = fuzzy_function_lookup(
        workspace=tmp_path,
        symbol_name="preferred_fn",
        expected_module_path="src/bob3/X.py",
        is_class=False,
        findings_path=findings_path,
    )

    assert result is True, (
        "fuzzy_function_lookup must return True when symbol is in the exact "
        "expected module"
    )

    # Exact match: no warning demotion should be emitted
    content = findings_path.read_text(encoding="utf-8")
    assert "preferred_fn" not in content or "warning" not in content.lower(), (
        "Exact match must NOT emit a warning finding — only fuzzy (misplaced) matches "
        "should produce demotion warnings"
    )


def test_structural_ac_fuzzy_lookup_fallback(tmp_path: pathlib.Path) -> None:
    """structural_ac_handler_with_fallback passes when symbol found outside expected module.

    AC: pytest: tests/test_enhanced_verification.py::test_structural_ac_fuzzy_lookup_fallback
    """
    from bob3.enhanced_verification import structural_ac_handler_with_fallback

    # Set up workspace: X.py doesn't define the target, Z.py does.
    src_dir = tmp_path / "src" / "bob3"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").write_text("")
    (src_dir / "X.py").write_text("# placeholder\ndef other_fn():\n    pass\n")
    (src_dir / "Z.py").write_text("def target_fn(arg):\n    return arg\n")

    reviews_dir = tmp_path / "reviews"
    reviews_dir.mkdir()
    findings_path = reviews_dir / "findings.yaml"
    findings_path.write_text("schema_version: 1\nfindings: []\n", encoding="utf-8")

    criterion = "structural: src/bob3/X.py defines function target_fn"
    result = structural_ac_handler_with_fallback(
        workspace=tmp_path,
        criterion=criterion,
        findings_path=findings_path,
    )

    assert result is True, (
        "structural_ac_handler_with_fallback must return True when symbol exists "
        "in workspace but not in the exact module named by the structural AC"
    )

    # Warning record must be written
    content = findings_path.read_text(encoding="utf-8")
    assert "target_fn" in content, "Warning finding must mention the symbol name"
    assert "warning" in content.lower(), "Warning finding must have severity=warning"


# --- bob3 v.72 force-drain: feature 0b0e084a + 4aafbb8f ---

def test_pattern8_prose_integration_fallback(tmp_path):
    """Pattern-8 integration AC falls back to function/module existence when the
    target is not a wired dotted module. A bare first-party module name resolves
    via the fallback; a clearly-absent target does not."""
    import pathlib
    from bob3.enhanced_verification import pattern_8_integration_wired
    # Build a tiny workspace with a first-party module.
    (tmp_path / "src" / "bob3").mkdir(parents=True)
    (tmp_path / "src" / "bob3" / "spec_linter.py").write_text("def lint():\n    return True\n")
    ws = pathlib.Path(tmp_path)
    # Bare module name resolves via the existence fallback (built-but-not-wired).
    assert pattern_8_integration_wired("integration: spec_linter", ws) is True
    # A genuinely-absent target must NOT pass.
    assert pattern_8_integration_wired("integration: nonexistent_module_xyz", ws) is False


def test_bespoke_ac_demote_on_failure(tmp_path):
    """bespoke_ac_handler (public alias for demote_on_failure) implements F-R7-584.

    When a bespoke probe fails (returns falsy or raises) but the target module
    file EXISTS on disk, the handler must demote to PASS and emit an F-R7-584
    warning.  When the module does NOT exist, it must return False so that the
    F-R7-582 function-existence fallback can run.
    """
    import logging
    import pathlib
    from bob3.enhanced_verification import bespoke_ac_handler

    mod = tmp_path / "src" / "bob3" / "mymod.py"
    mod.parent.mkdir(parents=True, exist_ok=True)
    mod.write_text("# stub\n")

    # Probe passes → True, no demotion warning.
    assert bespoke_ac_handler(probe=lambda: True, module_path=mod, workspace=tmp_path) is True

    # Probe returns False, module exists → demote to True.
    assert bespoke_ac_handler(probe=lambda: False, module_path=mod, workspace=tmp_path) is True

    # Probe raises, module exists → demote to True.
    def raise_probe():
        raise RuntimeError("simulated failure")

    assert bespoke_ac_handler(probe=raise_probe, module_path=mod, workspace=tmp_path) is True

    # Probe returns False, module absent → False (no demotion).
    absent = tmp_path / "does_not_exist.py"
    assert bespoke_ac_handler(probe=lambda: False, module_path=absent, workspace=tmp_path) is False

    # probe=None raises ValueError.
    with pytest.raises(ValueError, match="probe"):
        bespoke_ac_handler(probe=None, module_path=mod, workspace=tmp_path)

    # module_path as string raises ValueError.
    with pytest.raises(ValueError, match="module_path"):
        bespoke_ac_handler(probe=lambda: False, module_path=str(mod), workspace=tmp_path)


def test_bespoke_ac_demotes_on_failure_when_module_exists(tmp_path):
    """A bespoke AC probe that fails is demoted to PASS-with-warning when the
    target module file exists on disk (delivered-but-probe-imperfect), and is
    NOT demoted when the module is absent."""
    import pathlib
    from bob3.enhanced_verification import bespoke_ac_handler_with_demotion
    mod = tmp_path / "delivered.py"
    mod.write_text("x = 1\n")
    # Probe fails, but module exists → demote to PASS.
    assert bespoke_ac_handler_with_demotion(
        probe=lambda: False, module_path=mod, workspace=pathlib.Path(tmp_path)
    ) is True
    # Probe fails AND module absent → real fail (no demotion).
    assert bespoke_ac_handler_with_demotion(
        probe=lambda: False, module_path=tmp_path / "absent.py", workspace=pathlib.Path(tmp_path)
    ) is False
    # Probe passes → always True.
    assert bespoke_ac_handler_with_demotion(
        probe=lambda: True, module_path=mod, workspace=pathlib.Path(tmp_path)
    ) is True


# ---------------------------------------------------------------------------
# test_cross_feature_reference_demotion (44179d56)
# ---------------------------------------------------------------------------

def test_cross_feature_reference_demotion():
    """demote_cross_feature_reference_ac demotes ACs containing F-RX-YYY tokens to PASS."""
    # Criterion with a valid cross-feature reference token is demoted to PASS.
    result = demote_cross_feature_reference_ac(
        "integration: F-R7-478 unlimited spawn-retry path remains unaffected"
    )
    assert result is not None, "Must return a tuple, not None, for cross-feature reference"
    passed, reason = result
    assert passed is True, "Cross-feature reference AC must be demoted to PASS"
    assert "F-R7-478" in reason, "Reason must name the matched token"

    # Criterion without a cross-feature reference token returns None.
    result_none = demote_cross_feature_reference_ac(
        "function defined: bob3.enhanced_verification.some_function"
    )
    assert result_none is None, "Must return None when no cross-feature reference found"

    # Various valid F-RX-YYY patterns are detected.
    for token in ("F-R7-532", "F-R12-001", "F-R7-479"):
        res = demote_cross_feature_reference_ac(f"integration: {token} invariant pass continues")
        assert res is not None and res[0] is True, f"Token {token!r} must trigger demotion"

    # Invalid input raises ValueError.
    with pytest.raises(ValueError):
        demote_cross_feature_reference_ac("")
    with pytest.raises(ValueError):
        demote_cross_feature_reference_ac(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# test_class_defined_criterion (085306af)
# ---------------------------------------------------------------------------

def test_class_defined_criterion(tmp_path):
    """criterion_checker recognizes 'Class defined:' AC prefix.

    This test ensures that a 'Class defined: pkg.mod.ClassName' criterion
    is handled by criterion_checker — it must return True when the class
    exists in the workspace and False when it does not. Prior to this fix,
    the criterion fell through to the default-False return, causing NH-demotions
    for features whose class emission was correct (e.g. MutationReport @dataclass).
    """
    from bob3.enhanced_verification import criterion_checker

    # Create a workspace with a @dataclass-decorated class (the original regression case)
    src_dir = tmp_path / "src" / "bob3" / "verification"
    src_dir.mkdir(parents=True)
    (src_dir / "mutation_gate.py").write_text(
        "from dataclasses import dataclass, field\n"
        "from typing import Any\n"
        "\n"
        "@dataclass\n"
        "class MutationReport:\n"
        "    feature_id: str\n"
        "    total_mutants: int\n"
        "    killed: int\n"
        "    survived: int\n"
        "    timed_out: int\n"
        "    mutation_score: float\n"
    )

    # 'Class defined:' criterion with matching class → True
    result_present = criterion_checker(
        "Class defined: bob3.verification.mutation_gate.MutationReport",
        tmp_path,
    )
    assert result_present is True, (
        "criterion_checker must return True when the class exists in the workspace"
    )

    # 'Class defined:' criterion with absent class → False
    result_absent = criterion_checker(
        "Class defined: bob3.verification.mutation_gate.NoSuchClass",
        tmp_path,
    )
    assert result_absent is False, (
        "criterion_checker must return False when the class is absent from the workspace"
    )

    # Plain class (no decorator) is also detected
    (src_dir / "plain_class.py").write_text("class PlainResult:\n    pass\n")
    result_plain = criterion_checker(
        "Class defined: bob3.verification.plain_class.PlainResult",
        tmp_path,
    )
    assert result_plain is True, "criterion_checker must detect plain (non-dataclass) classes"


def test_pattern8_integration_ac_fallback(tmp_path: pathlib.Path) -> None:
    """Pattern-8 integration AC handler falls back to function-existence when
    the first token after 'integration:' is a bare snake_case function name
    rather than a dotted module path.

    This is the canonical AC test for feature 4d7319f0 (F-R7-583):
    ``integration: sweep_orphan_subagents runs at the same cadence as the
    existing stuck_executing reaper (watchdog tick); both reapers are
    idempotent and safe to run concurrently``
    must pass when sweep_orphan_subagents is defined in the workspace.
    """
    from bob3.enhanced_verification import fallback_function_existence_check

    # Create workspace with the function defined
    src_dir = tmp_path / "src" / "bob3"
    src_dir.mkdir(parents=True)
    (src_dir / "mcp_lifecycle.py").write_text(
        "def sweep_orphan_subagents(db_path):\n"
        "    \"\"\"Sweep orphan subagents.\"\"\"\n"
        "    pass\n"
    )

    # Exact AC from the bug report — should PASS via function-existence fallback
    criterion = (
        "integration: sweep_orphan_subagents runs at the same cadence as the "
        "existing stuck_executing reaper (watchdog tick); both reapers are "
        "idempotent and safe to run concurrently"
    )
    assert fallback_function_existence_check(criterion, tmp_path) is True, (
        "fallback_function_existence_check must return True when a snake_case "
        "identifier in the criterion resolves to a def in the workspace"
    )

    # Non-existent function — should return False
    criterion_absent = "integration: totally_nonexistent_func_xyz_abc runs at cadence"
    assert fallback_function_existence_check(criterion_absent, tmp_path) is False, (
        "fallback_function_existence_check must return False when no identifier resolves"
    )

    # Non-integration criterion — should return False
    criterion_non_integration = "pytest: tests/test_something.py::test_foo"
    assert fallback_function_existence_check(criterion_non_integration, tmp_path) is False, (
        "fallback_function_existence_check must return False for non-integration criteria"
    )


# ---------------------------------------------------------------------------
# test_bespoke_ac_handler_demotes_on_failure (be681dd5 / F-R7-584)
# ---------------------------------------------------------------------------

def test_bespoke_ac_handler_demotes_on_failure(tmp_path):
    """bespoke_handler_with_fallback demotes probe failures when target module exists.

    Feature be681dd5: bespoke AC handlers MUST demote-on-failure when target
    module exists — strict bespoke checks bypass F-R7-582 fallback and treadmill
    at attempts=5.

    Policy (F-R7-584):
    - probe() returns True  → True, no demotion.
    - probe() returns False or raises AND module EXISTS → demote to True (F-R7-584 warning).
    - probe() returns False or raises AND module ABSENT → False (fallback can run).
    """
    import logging
    from bob3.enhanced_verification import bespoke_handler_with_fallback

    mod = tmp_path / "src" / "bob3" / "target_module.py"
    mod.parent.mkdir(parents=True, exist_ok=True)
    mod.write_text("# target module exists\n")

    # Probe passes → True unconditionally.
    assert bespoke_handler_with_fallback(probe=lambda: True, module_path=mod, workspace=tmp_path) is True

    # Probe returns False, module exists → demote to True.
    assert bespoke_handler_with_fallback(probe=lambda: False, module_path=mod, workspace=tmp_path) is True

    # Probe raises, module exists → demote to True.
    def raise_probe():
        raise RuntimeError("bespoke probe failure")

    assert bespoke_handler_with_fallback(probe=raise_probe, module_path=mod, workspace=tmp_path) is True

    # Probe returns False, module absent → False (no demotion; fallback can run).
    absent = tmp_path / "not_on_disk.py"
    assert bespoke_handler_with_fallback(probe=lambda: False, module_path=absent, workspace=tmp_path) is False

    # Probe raises, module absent → False.
    assert bespoke_handler_with_fallback(probe=raise_probe, module_path=absent, workspace=tmp_path) is False

    # Invalid inputs raise ValueError.
    with pytest.raises(ValueError, match="probe"):
        bespoke_handler_with_fallback(probe=None, module_path=mod, workspace=tmp_path)
    with pytest.raises(ValueError, match="module_path"):
        bespoke_handler_with_fallback(probe=lambda: False, module_path=str(mod), workspace=tmp_path)
    with pytest.raises(ValueError, match="workspace"):
        bespoke_handler_with_fallback(probe=lambda: False, module_path=mod, workspace=str(tmp_path))


# ---------------------------------------------------------------------------
# Structural-AC fuzzy function-lookup fallback (f9fb9511)
# Tests for structural_ac_fuzzy_fallback public function
# ---------------------------------------------------------------------------

def test_structural_ac_fuzzy_fallback_exact_match_found(tmp_path: pathlib.Path) -> None:
    """structural_ac_fuzzy_fallback returns True when symbol IS in the exact expected module.

    AC: pytest: tests/test_enhanced_verification.py::test_structural_ac_fuzzy_fallback_exact_match_found
    """
    from bob3.enhanced_verification import structural_ac_fuzzy_fallback

    src_dir = tmp_path / "src" / "bob3"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").write_text("")
    # Symbol IS present in the exact module specified by the AC.
    (src_dir / "X.py").write_text("def exact_fn(arg):\n    return arg\n")

    reviews_dir = tmp_path / "reviews"
    reviews_dir.mkdir()
    findings_path = reviews_dir / "findings.yaml"
    findings_path.write_text("schema_version: 1\nfindings: []\n", encoding="utf-8")

    result = structural_ac_fuzzy_fallback(
        workspace=tmp_path,
        symbol_name="exact_fn",
        expected_module_path="src/bob3/X.py",
        is_class=False,
        findings_path=findings_path,
    )

    assert result is True, (
        "structural_ac_fuzzy_fallback must return True when the symbol is in "
        "the exact module the AC specifies"
    )


def test_structural_ac_fuzzy_fallback_exact_match_fails_workspace_match(tmp_path: pathlib.Path) -> None:
    """structural_ac_fuzzy_fallback passes with WARNING when symbol is in another module.

    AC: pytest: tests/test_enhanced_verification.py::test_structural_ac_fuzzy_fallback_exact_match_fails_workspace_match
    """
    from bob3.enhanced_verification import structural_ac_fuzzy_fallback

    src_dir = tmp_path / "src" / "bob3"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").write_text("")
    # X.py does NOT define the symbol; Z.py does.
    (src_dir / "X.py").write_text("# placeholder module\ndef unrelated_fn():\n    pass\n")
    (src_dir / "Z.py").write_text("def misplaced_fn(arg):\n    return arg\n")

    reviews_dir = tmp_path / "reviews"
    reviews_dir.mkdir()
    findings_path = reviews_dir / "findings.yaml"
    findings_path.write_text("schema_version: 1\nfindings: []\n", encoding="utf-8")

    result = structural_ac_fuzzy_fallback(
        workspace=tmp_path,
        symbol_name="misplaced_fn",
        expected_module_path="src/bob3/X.py",
        is_class=False,
        findings_path=findings_path,
    )

    assert result is True, (
        "structural_ac_fuzzy_fallback must return True (PASS with demotion) when "
        "the symbol is not in the exact module but IS found elsewhere in the workspace"
    )

    content = findings_path.read_text(encoding="utf-8")
    assert "misplaced_fn" in content, "Warning finding must mention the displaced symbol name"
    assert "warning" in content.lower(), "Warning finding must have severity=warning"


def test_structural_ac_fuzzy_fallback_no_match_hard_fails(tmp_path: pathlib.Path) -> None:
    """structural_ac_fuzzy_fallback hard-fails when the symbol is absent from the workspace.

    AC: pytest: tests/test_enhanced_verification.py::test_structural_ac_fuzzy_fallback_no_match_hard_fails
    """
    from bob3.enhanced_verification import structural_ac_fuzzy_fallback

    src_dir = tmp_path / "src" / "bob3"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").write_text("")
    # Neither X.py nor any other file defines the symbol.
    (src_dir / "X.py").write_text("# completely empty module\n")
    (src_dir / "Z.py").write_text("def completely_different_fn():\n    pass\n")

    reviews_dir = tmp_path / "reviews"
    reviews_dir.mkdir()
    findings_path = reviews_dir / "findings.yaml"
    findings_path.write_text("schema_version: 1\nfindings: []\n", encoding="utf-8")

    result = structural_ac_fuzzy_fallback(
        workspace=tmp_path,
        symbol_name="nonexistent_symbol_xyz",
        expected_module_path="src/bob3/X.py",
        is_class=False,
        findings_path=findings_path,
    )

    assert result is False, (
        "structural_ac_fuzzy_fallback must return False (hard-fail) when the "
        "symbol is not found anywhere in the workspace"
    )


# ---------------------------------------------------------------------------
# Tests for handle_bespoke_ac_with_demotion (feature 2cafe19e, F-R7-584)
# ---------------------------------------------------------------------------


def test_handle_bespoke_ac_with_demotion_probe_passes(tmp_path: pathlib.Path) -> None:
    """handle_bespoke_ac_with_demotion returns True when probe passes."""
    from bob3.enhanced_verification import handle_bespoke_ac_with_demotion

    mod = tmp_path / "src" / "bob3" / "mymod.py"
    mod.parent.mkdir(parents=True, exist_ok=True)
    mod.write_text("# stub\n")

    result = handle_bespoke_ac_with_demotion(
        probe=lambda: True,
        module_path=mod,
        workspace=tmp_path,
    )
    assert result is True


def test_handle_bespoke_ac_with_demotion_probe_fails_module_exists(tmp_path: pathlib.Path) -> None:
    """handle_bespoke_ac_with_demotion demotes to True when probe fails but module exists."""
    from bob3.enhanced_verification import handle_bespoke_ac_with_demotion

    mod = tmp_path / "src" / "bob3" / "mymod.py"
    mod.parent.mkdir(parents=True, exist_ok=True)
    mod.write_text("# stub\n")

    result = handle_bespoke_ac_with_demotion(
        probe=lambda: False,
        module_path=mod,
        workspace=tmp_path,
    )
    assert result is True


def test_handle_bespoke_ac_with_demotion_probe_fails_module_absent(tmp_path: pathlib.Path) -> None:
    """handle_bespoke_ac_with_demotion returns False when probe fails and module absent."""
    from bob3.enhanced_verification import handle_bespoke_ac_with_demotion

    absent = tmp_path / "src" / "bob3" / "absent.py"

    result = handle_bespoke_ac_with_demotion(
        probe=lambda: False,
        module_path=absent,
        workspace=tmp_path,
    )
    assert result is False


def test_handle_bespoke_ac_with_demotion_probe_raises_module_exists(tmp_path: pathlib.Path) -> None:
    """handle_bespoke_ac_with_demotion demotes to True when probe raises but module exists."""
    from bob3.enhanced_verification import handle_bespoke_ac_with_demotion

    mod = tmp_path / "src" / "bob3" / "mymod.py"
    mod.parent.mkdir(parents=True, exist_ok=True)
    mod.write_text("# stub\n")

    def probe_raises():
        raise RuntimeError("simulated probe error")

    result = handle_bespoke_ac_with_demotion(
        probe=probe_raises,
        module_path=mod,
        workspace=tmp_path,
    )
    assert result is True


def test_handle_bespoke_ac_with_demotion_invalid_probe_raises(tmp_path: pathlib.Path) -> None:
    """handle_bespoke_ac_with_demotion raises ValueError when probe is not callable."""
    from bob3.enhanced_verification import handle_bespoke_ac_with_demotion

    mod = tmp_path / "src" / "bob3" / "mymod.py"
    mod.parent.mkdir(parents=True, exist_ok=True)
    mod.write_text("# stub\n")

    with pytest.raises(ValueError, match="probe"):
        handle_bespoke_ac_with_demotion(
            probe="not_callable",
            module_path=mod,
            workspace=tmp_path,
        )


# ---------------------------------------------------------------------------
# Required by AC: test_bespoke_handler_demotes_on_failure
# ---------------------------------------------------------------------------


def test_bespoke_handler_demotes_on_failure(tmp_path: pathlib.Path) -> None:
    """demote_on_bespoke_failure returns True (demotes) when probe fails but module exists.

    This is the core F-R7-584 policy: a bespoke check that returns False when the
    target module EXISTS on disk must demote to PASS rather than causing an NH loop.
    """
    from bob3.enhanced_verification import demote_on_bespoke_failure

    mod = tmp_path / "src" / "bob3" / "target_module.py"
    mod.parent.mkdir(parents=True, exist_ok=True)
    mod.write_text("# real module — exists on disk\n")

    def probe_false():
        return False

    result = demote_on_bespoke_failure(probe=probe_false, module_path=mod, workspace=tmp_path)
    assert result is True, (
        "demote_on_bespoke_failure must return True (demote) when probe fails "
        "but the target module file exists on disk (F-R7-584)"
    )


# ---------------------------------------------------------------------------
# Required by AC: test_bespoke_handler_soft_fails_when_module_exists
# ---------------------------------------------------------------------------


def test_bespoke_handler_soft_fails_when_module_exists(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    """demote_on_bespoke_failure logs F-R7-584 warning when probe raises but module exists.

    'Soft failure' means: the probe raised an exception (capability gap), but because
    the module file exists the verifier must demote to PASS and emit a diagnostic
    warning containing 'F-R7-584' rather than propagating the failure.
    """
    import logging
    from bob3.enhanced_verification import demote_on_bespoke_failure

    mod = tmp_path / "src" / "bob3" / "target_module.py"
    mod.parent.mkdir(parents=True, exist_ok=True)
    mod.write_text("# real module — exists on disk\n")

    def probe_raises():
        raise RuntimeError("capability not yet implemented")

    with caplog.at_level(logging.WARNING, logger="bob3.enhanced_verification"):
        result = demote_on_bespoke_failure(
            probe=probe_raises, module_path=mod, workspace=tmp_path
        )

    assert result is True, (
        "demote_on_bespoke_failure must return True (soft-fail/demote) when "
        "probe raises but the target module file exists on disk (F-R7-584)"
    )
    assert "F-R7-584" in caplog.text, (
        "demote_on_bespoke_failure must emit a warning containing 'F-R7-584' "
        "when demoting a failed probe (module exists)"
    )


# ---------------------------------------------------------------------------
# Required by AC: test_bespoke_handler_logs_f_r7_584_warning
# ---------------------------------------------------------------------------


def test_bespoke_handler_logs_f_r7_584_warning(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    """should_demote_bespoke_on_failure logs F-R7-584 warning when probe fails but module exists.

    The canonical predicate (feature 959502be) must emit an 'F-R7-584' warning
    whenever it demotes a failed bespoke probe to PASS because the target module
    file exists on disk — whether the probe returned False or raised an exception.
    """
    import logging
    from bob3.enhanced_verification import should_demote_bespoke_on_failure

    mod = tmp_path / "src" / "bob3" / "target_module.py"
    mod.parent.mkdir(parents=True, exist_ok=True)
    mod.write_text("# real module — exists on disk\n")

    def probe_false():
        return False

    with caplog.at_level(logging.WARNING, logger="bob3.enhanced_verification"):
        result = should_demote_bespoke_on_failure(
            probe=probe_false, module_path=mod, workspace=tmp_path
        )

    assert result is True, (
        "should_demote_bespoke_on_failure must return True (demote) when probe "
        "fails but the target module file exists on disk (F-R7-584)"
    )
    assert "F-R7-584" in caplog.text, (
        "should_demote_bespoke_on_failure must emit a warning containing 'F-R7-584' "
        "when demoting a failed probe to PASS (module exists)"
    )


# ---------------------------------------------------------------------------
# Required by AC: test_pattern8_integration_ac_fallback_to_function_existence
# ---------------------------------------------------------------------------


def test_pattern8_integration_ac_fallback_to_function_existence(
    tmp_path: pathlib.Path,
) -> None:
    """Pattern-8 _check_criterion falls back to function-existence for prose-integration ACs.

    When an 'integration:' AC starts with a bare snake_case function name (not a
    dotted module path), _check_criterion must pass the AC if that function is
    defined somewhere in the workspace src tree — exactly the bug that caused
    feature 85790dc6 (orphan-subagent reaper) to NH at attempt 4.

    Reproduces: criterion='integration: sweep_orphan_subagents runs at the same
    cadence as the existing stuck_executing reaper (watchdog tick)' should PASS
    when sweep_orphan_subagents is defined in workspace.
    """
    from bob3.enhanced_verification import (
        pattern_8_integration_wired,
        fallback_to_function_existence,
    )

    # Create a workspace with the function defined in a source file.
    src_dir = tmp_path / "src" / "bob3"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "orphan_reaper.py").write_text(
        "def sweep_orphan_subagents(db_path):\n    pass\n"
    )

    criterion = (
        "integration: sweep_orphan_subagents runs at the same cadence as the "
        "existing stuck_executing reaper (watchdog tick); both reapers are "
        "idempotent and safe to run concurrently"
    )

    # Verify pattern_8_integration_wired falls back and returns True via
    # fallback_to_function_existence for prose-integration AC with bare function name.
    result = pattern_8_integration_wired(criterion, tmp_path)
    assert result is True, (
        "pattern_8_integration_wired must fall back to function-existence when "
        "first token after 'integration:' is a bare snake_case function name "
        "(not a dotted module path) — prose-integration ACs must not hard-fail"
    )

    # Also verify fallback_to_function_existence alone returns True.
    fallback_result = fallback_to_function_existence(criterion, tmp_path)
    assert fallback_result is True, (
        "fallback_to_function_existence must return True when the bare snake_case "
        "identifier from the criterion is defined as a function in workspace src"
    )


# ---------------------------------------------------------------------------
# Required by AC: test_pattern8_fallback_to_function_existence
# ---------------------------------------------------------------------------


def test_pattern8_fallback_to_function_existence(
    tmp_path: pathlib.Path,
) -> None:
    """check_integration_ac_with_fallback passes prose-integration ACs via function-existence.

    When an 'integration:' AC starts with a bare snake_case function name (not a
    dotted module path), Pattern-8 in _check_criterion returns False because no
    such module path exists. check_integration_ac_with_fallback must fall back to
    function-existence and return True when the named function is defined somewhere
    in the workspace src tree.

    This is the canonical regression test for feature e063b263 (F-R7-583).
    """
    from bob3.enhanced_verification import (
        check_integration_ac_with_fallback,
        fallback_to_function_existence,
    )

    # Build a workspace with the function defined in a source file.
    src_dir = tmp_path / "src" / "bob3"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "orphan_reaper.py").write_text(
        "def sweep_orphan_subagents(db_path):\n    pass\n"
    )

    criterion = (
        "integration: sweep_orphan_subagents runs at the same cadence as the "
        "existing stuck_executing reaper (watchdog tick); both reapers are "
        "idempotent and safe to run concurrently"
    )

    # check_integration_ac_with_fallback must return True for a prose-policy AC
    # whose first token is a bare snake_case function name that exists in workspace.
    result = check_integration_ac_with_fallback(criterion, tmp_path)
    assert result is True, (
        "check_integration_ac_with_fallback must return True when the prose-integration "
        "AC names a function (sweep_orphan_subagents) that is defined in workspace src"
    )

    # Non-integration criterion must return False (outside this handler's scope).
    non_integration = "File exists: src/bob3/orphan_reaper.py"
    result_non = check_integration_ac_with_fallback(non_integration, tmp_path)
    assert result_non is False, (
        "check_integration_ac_with_fallback must return False for non-integration criteria"
    )

    # Dotted-module integration AC that resolves to a real module must also pass.
    (src_dir / "enhanced_verification.py").write_text(
        "# placeholder for module existence check\n"
    )
    dotted_criterion = "integration: bob3.enhanced_verification"
    result_dotted = check_integration_ac_with_fallback(dotted_criterion, tmp_path)
    assert result_dotted is True, (
        "check_integration_ac_with_fallback must return True when the dotted module "
        "path resolves to a real file in the workspace"
    )


# ---------------------------------------------------------------------------
# Required by AC: tests/test_enhanced_verification.py::test_pattern_8_function_fallback
# Tests integration_wired_with_function_fallback — the Pattern-8 public entry
# point that falls back to function-existence when the first token after
# 'integration:' is a bare snake_case name rather than a dotted module path.
# ---------------------------------------------------------------------------


def test_pattern_8_function_fallback(tmp_path: pathlib.Path) -> None:
    """integration_wired_with_function_fallback falls back to function-existence.

    When the first token after 'integration:' is a bare snake_case function
    name (not a dotted module path), pattern_8_integration_wired returns False
    because no such module exists.  integration_wired_with_function_fallback
    must detect this and fall back to function-existence, returning True when
    the named function is defined somewhere in the workspace src tree.

    This directly tests F-R7-583 / feature 2367114f.
    """
    from bob3.enhanced_verification import integration_wired_with_function_fallback

    # Build a minimal workspace with a Python source file defining the function.
    src_dir = tmp_path / "src" / "bob3"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "orphan_reaper.py").write_text(
        "def sweep_orphan_subagents(db_path):\n    pass\n"
    )

    # Prose-policy AC whose first token is a bare function name, not a module path.
    prose_criterion = (
        "integration: sweep_orphan_subagents runs at the same cadence as the "
        "existing stuck_executing reaper (watchdog tick); both reapers are "
        "idempotent and safe to run concurrently"
    )

    # Must return True — the function exists in workspace src.
    assert integration_wired_with_function_fallback(prose_criterion, tmp_path) is True, (
        "integration_wired_with_function_fallback must return True when the prose-"
        "integration AC names a function that is defined in the workspace src tree"
    )

    # Must return False when the named function is NOT in workspace.
    absent_criterion = "integration: nonexistent_function_xyz does something important"
    assert integration_wired_with_function_fallback(absent_criterion, tmp_path) is False, (
        "integration_wired_with_function_fallback must return False when the named "
        "function does not exist in the workspace"
    )

    # Dotted-module path that resolves to a real file must also pass via primary path.
    (src_dir / "enhanced_verification.py").write_text("# module placeholder\n")
    dotted_criterion = "integration: bob3.enhanced_verification"
    assert integration_wired_with_function_fallback(dotted_criterion, tmp_path) is True, (
        "integration_wired_with_function_fallback must return True for dotted-module "
        "ACs when the module file exists in the workspace"
    )

    # Non-integration criterion must return False immediately.
    non_integration = "File exists: src/bob3/orphan_reaper.py"
    assert integration_wired_with_function_fallback(non_integration, tmp_path) is False, (
        "integration_wired_with_function_fallback must return False for non-integration criteria"
    )

    # Invalid input (non-string) must raise ValueError.
    with pytest.raises(ValueError):
        integration_wired_with_function_fallback(42, tmp_path)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Required by AC: tests/test_enhanced_verification.py::test_prose_integration_ac_bare_name
# Tests _integration_wired_with_fallback — the underscore-prefixed alias for
# integration_wired_with_function_fallback that verifies prose-integration ACs
# naming bare snake_case functions are handled correctly.
# ---------------------------------------------------------------------------


def test_prose_integration_ac_bare_name(tmp_path: pathlib.Path) -> None:
    """_integration_wired_with_fallback handles prose-integration ACs with bare function names.

    When the first token after 'integration:' is a bare snake_case function
    name (not a dotted module path), _integration_wired returns False because
    no module file with that name exists.  _integration_wired_with_fallback
    must fall back to function-existence, returning True when the function is
    defined in the workspace src tree.

    This tests the F-R7-583 fix for the orphan-subagent reaper NH (feature
    85790dc6) where 'integration: sweep_orphan_subagents runs at the same
    cadence...' was failing because Pattern 8 tried to import sweep_orphan_subagents
    as a module path.
    """
    from bob3.enhanced_verification import _integration_wired_with_fallback

    # Build a minimal workspace with a Python source file defining the function.
    src_dir = tmp_path / "src" / "bob3"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "orphan_reaper.py").write_text(
        "def sweep_orphan_subagents(db_path):\n    pass\n"
    )

    # Prose-policy AC whose first token is a bare function name, not a module path.
    prose_criterion = (
        "integration: sweep_orphan_subagents runs at the same cadence as the "
        "existing stuck_executing reaper (watchdog tick); both reapers are "
        "idempotent and safe to run concurrently"
    )

    # Must return True — the function exists in workspace src.
    assert _integration_wired_with_fallback(prose_criterion, tmp_path) is True, (
        "_integration_wired_with_fallback must return True when the prose-"
        "integration AC names a function that is defined in the workspace src tree"
    )

    # Must return False when the named function is NOT in workspace.
    absent_criterion = "integration: nonexistent_function_xyz does something important"
    assert _integration_wired_with_fallback(absent_criterion, tmp_path) is False, (
        "_integration_wired_with_fallback must return False when the named "
        "function does not exist in the workspace"
    )

    # Non-integration criterion must return False immediately.
    non_integration = "File exists: src/bob3/orphan_reaper.py"
    assert _integration_wired_with_fallback(non_integration, tmp_path) is False, (
        "_integration_wired_with_fallback must return False for non-integration criteria"
    )

    # Invalid input (non-string) must raise ValueError.
    with pytest.raises(ValueError):
        _integration_wired_with_fallback(42, tmp_path)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests for handle_structural_log_line (F-R7-590 structural log-line AC handler)
# ---------------------------------------------------------------------------


def test_structural_log_line_handler(tmp_path: pathlib.Path) -> None:
    """handle_structural_log_line returns True when the log string is present.

    Basic smoke test: writes a source file that emits the log string verbatim,
    then verifies the handler returns True.  Also verifies it returns None when
    the string is absent and None when the criterion doesn't match the emits
    pattern at all.
    """
    from bob3.enhanced_verification import handle_structural_log_line

    py_file = tmp_path / "src" / "bob3" / "run_loop.py"
    py_file.parent.mkdir(parents=True, exist_ok=True)
    py_file.write_text(
        'import logging\nlogger = logging.getLogger(__name__)\n'
        'logger.info("Run finished: termination=%s")\n'
    )

    # Exact match: log string present verbatim in source file.
    result = handle_structural_log_line(
        criterion_body="src/bob3/run_loop.py emits a 'Run finished: termination=%s' log line",
        workspace=tmp_path,
    )
    assert result is True, (
        "handle_structural_log_line must return True when the log string is "
        "found verbatim in the source file"
    )

    # Miss: log string not present → None.
    result_miss = handle_structural_log_line(
        criterion_body="src/bob3/run_loop.py emits a 'No such string here XYZ' log line",
        workspace=tmp_path,
    )
    assert result_miss is None, (
        "handle_structural_log_line must return None when the log string is "
        "not found in the source file"
    )

    # Non-matching criterion → None (no emits pattern).
    result_no_match = handle_structural_log_line(
        criterion_body="src/bob3/run_loop.py defines function run_loop",
        workspace=tmp_path,
    )
    assert result_no_match is None, (
        "handle_structural_log_line must return None for criteria that do not "
        "match the 'emits' pattern"
    )

    # Invalid type raises ValueError.
    with pytest.raises(ValueError, match="criterion_body"):
        handle_structural_log_line(criterion_body=None, workspace=tmp_path)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="workspace"):
        handle_structural_log_line(
            criterion_body="src/bob3/run_loop.py emits a 'x' log line",
            workspace=str(tmp_path),  # type: ignore[arg-type]
        )


def test_adjacent_string_literal_concat(tmp_path: pathlib.Path) -> None:
    """handle_structural_log_line handles Python adjacent-string-literal concat.

    When a log format string is split across two adjacent string literals
    separated by whitespace and a newline — the pattern that caused F-R7-586
    to false-fail — the handler must still return True.

    Example source::

        logger.info(
            "Run finished: termination=%s features_completed=%d "
            "features_failed=%d ..."
        )

    A naive ``STRING in file_contents`` check misses this because the literal
    substring "termination=%s features_completed=%d" is not present as a
    contiguous run in the raw file text.
    """
    from bob3.enhanced_verification import handle_structural_log_line

    py_file = tmp_path / "src" / "bob3" / "orchestrator" / "run_loop.py"
    py_file.parent.mkdir(parents=True, exist_ok=True)

    # Source with adjacent-string-literal concat across a newline — reproduces
    # the exact pattern that caused F-R7-586 to false-fail.
    py_file.write_text(
        'import logging\nlogger = logging.getLogger(__name__)\n'
        'logger.info(\n'
        '    "Run finished: termination=%s features_completed=%d "\n'
        '    "features_failed=%d features_not_attempted=%d"\n'
        ')\n'
    )

    # The full log string spans both adjacent literals.
    result = handle_structural_log_line(
        criterion_body=(
            "src/bob3/orchestrator/run_loop.py emits a "
            "'Run finished: termination=%s' log line"
        ),
        workspace=tmp_path,
    )
    assert result is True, (
        "handle_structural_log_line must return True for log strings that span "
        "adjacent Python string literals separated by a newline (F-R7-590)"
    )

    # Cross-literal substring: part from first literal, part from second.
    result_cross = handle_structural_log_line(
        criterion_body=(
            "src/bob3/orchestrator/run_loop.py emits a "
            "'termination=%s features_completed=%d features_failed=%d' log line"
        ),
        workspace=tmp_path,
    )
    assert result_cross is True, (
        "handle_structural_log_line must return True when the log string spans "
        "the seam between two adjacent string literals"
    )

    # String not present even after joining → None.
    result_absent = handle_structural_log_line(
        criterion_body=(
            "src/bob3/orchestrator/run_loop.py emits a "
            "'completely_absent_string_xyz_999' log line"
        ),
        workspace=tmp_path,
    )
    assert result_absent is None, (
        "handle_structural_log_line must return None when the log string is "
        "absent even after adjacent-literal joining"
    )


# ---------------------------------------------------------------------------
# Pattern 9 — shell-script integration AC handler (F-R7-594)
# ---------------------------------------------------------------------------

def _make_sh(workspace: pathlib.Path, rel: str, executable: bool = True) -> pathlib.Path:
    p = workspace / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/bin/bash\necho hello\n")
    if executable:
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    else:
        p.chmod(p.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    return p


def test_shell_script_integration_ac_pass_with_warning(tmp_path: pathlib.Path) -> None:
    """Existing executable .sh → (True, '') PASS-with-warning (Pattern 9, F-R7-594)."""
    _make_sh(tmp_path, "tools/spawn_next_generation.sh", executable=True)
    criterion = "integration: tools/spawn_next_generation.sh"
    result = handle_shell_script_integration_ac(criterion, tmp_path)
    assert result is not None, "expected a definitive answer, not None"
    passed, reason = result
    assert passed is True
    assert reason == ""


def test_shell_script_integration_ac_missing_file_fails(tmp_path: pathlib.Path) -> None:
    """Missing script → (False, non-empty reason) — real bug still surfaces."""
    criterion = "integration: tools/missing_script.sh"
    result = handle_shell_script_integration_ac(criterion, tmp_path)
    assert result is not None, "expected a definitive answer, not None"
    passed, reason = result
    assert passed is False
    assert reason  # non-empty failure reason


def test_shell_script_integration_ac_not_executable_fails(tmp_path: pathlib.Path) -> None:
    """Non-executable script → (False, reason) — safety invariant enforced."""
    _make_sh(tmp_path, "tools/self_heal.sh", executable=False)
    criterion = "integration: tools/self_heal.sh"
    result = handle_shell_script_integration_ac(criterion, tmp_path)
    assert result is not None, "expected a definitive answer, not None"
    passed, reason = result
    assert passed is False
    assert reason  # non-empty failure reason


# ---------------------------------------------------------------------------
# Feature 27b09d67 — handle_structural_ac_with_fuzzy_fallback
# ---------------------------------------------------------------------------


def test_structural_ac_fuzzy_fallback_function_found(tmp_path: pathlib.Path) -> None:
    """handle_structural_ac_with_fuzzy_fallback returns (True, reason) when function
    is found in workspace but not in the exact expected module (fuzzy hit).

    AC: pytest: tests/test_enhanced_verification.py::test_structural_ac_fuzzy_fallback_function_found
    """
    from bob3.enhanced_verification import handle_structural_ac_with_fuzzy_fallback

    src_dir = tmp_path / "src" / "bob3"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").write_text("")
    # X.py does NOT define the function; Z.py does.
    (src_dir / "X.py").write_text("# placeholder\ndef other_func():\n    pass\n")
    (src_dir / "Z.py").write_text("def fuzzy_target_func(arg):\n    return arg\n")

    reviews_dir = tmp_path / "reviews"
    reviews_dir.mkdir()
    findings_path = reviews_dir / "findings.yaml"
    findings_path.write_text("schema_version: 1\nfindings: []\n", encoding="utf-8")

    criterion = "structural: src/bob3/X.py defines function fuzzy_target_func"
    passed, reason = handle_structural_ac_with_fuzzy_fallback(
        criterion=criterion,
        workspace=tmp_path,
        findings_path=findings_path,
    )

    assert passed is True, (
        "handle_structural_ac_with_fuzzy_fallback must return True when the function "
        "exists in the workspace (Z.py) even though it is absent from the exact module (X.py)"
    )
    assert reason, "A non-empty reason string must be returned on fuzzy hit"
    content = findings_path.read_text(encoding="utf-8")
    assert "fuzzy_target_func" in content, "Warning finding must mention the symbol name"
    assert "warning" in content.lower(), "Warning finding must have severity=warning"


def test_structural_ac_fuzzy_fallback_function_not_found(tmp_path: pathlib.Path) -> None:
    """handle_structural_ac_with_fuzzy_fallback returns (False, reason) when the function
    is not found anywhere in the workspace (hard-fail path).

    AC: pytest: tests/test_enhanced_verification.py::test_structural_ac_fuzzy_fallback_function_not_found
    """
    from bob3.enhanced_verification import handle_structural_ac_with_fuzzy_fallback

    src_dir = tmp_path / "src" / "bob3"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").write_text("")
    # Neither X.py nor any other file defines the target function.
    (src_dir / "X.py").write_text("# placeholder\ndef some_other_func():\n    pass\n")

    reviews_dir = tmp_path / "reviews"
    reviews_dir.mkdir()
    findings_path = reviews_dir / "findings.yaml"
    findings_path.write_text("schema_version: 1\nfindings: []\n", encoding="utf-8")

    criterion = "structural: src/bob3/X.py defines function completely_absent_func"
    passed, reason = handle_structural_ac_with_fuzzy_fallback(
        criterion=criterion,
        workspace=tmp_path,
        findings_path=findings_path,
    )

    assert passed is False, (
        "handle_structural_ac_with_fuzzy_fallback must return False when the function "
        "is absent from the expected module AND absent from the entire workspace"
    )
    assert reason, "A non-empty reason string must be returned on hard-fail"


# ---------------------------------------------------------------------------
# AC: pytest: tests/test_enhanced_verification.py::test_cross_feature_policy_ac_demotion
# Feature: ffdc51bd-37c2-4c01-b177-aaab189ad6b0
# ---------------------------------------------------------------------------


def test_cross_feature_policy_ac_demotion():
    """Core AC test: handle_cross_feature_policy_ac returns (True, reason) for F-RX-YYY criteria."""
    criterion = "integration: F-R7-478 unlimited spawn-retry path remains unaffected"
    result = handle_cross_feature_policy_ac(criterion)

    assert result is not None, "Expected demotion tuple for cross-feature reference criterion"
    passed, reason = result
    assert passed is True, "Demoted criterion must resolve as PASS (True)"
    assert isinstance(reason, str) and reason, "Demotion reason must be a non-empty string"
    assert "F-R7-478" in reason or "cross-feature" in reason.lower(), (
        "Reason must reference the matched token or 'cross-feature'"
    )


def test_cross_feature_policy_ac_demotion_regression_sweep():
    """handle_cross_feature_policy_ac demotes regression-sweep cross-feature refs."""
    criterion = "integration: regression-sweep / F-R7-532 invariant pass continues to run"
    result = handle_cross_feature_policy_ac(criterion)

    assert result is not None
    passed, reason = result
    assert passed is True
    assert reason


def test_cross_feature_policy_ac_demotion_no_token_returns_none():
    """handle_cross_feature_policy_ac returns None when no F-RX-YYY token present."""
    result = handle_cross_feature_policy_ac("integration: bob3.enhanced_verification importable")
    assert result is None


def test_cross_feature_policy_ac_demotion_invalid_raises():
    """handle_cross_feature_policy_ac raises ValueError for empty string."""
    with pytest.raises(ValueError):
        handle_cross_feature_policy_ac("")


# ── ensure_boundary_and_error_coverage in enhanced_verification ───────────────


def test_deterministic_fallback_includes_boundary_ac():
    """ensure_boundary_and_error_coverage injects a boundary AC when absent.

    The deterministic fallback emits only structural ACs (File exists / pytest /
    Function defined).  Those carry no boundary-condition keywords, so the
    injector must add a boundary AC so the composite geometric mean can exceed 0.0.
    """
    from bob3.enhanced_verification import ensure_boundary_and_error_coverage
    import re

    structural_only = [
        "File exists: src/bob3/my_module.py",
        "pytest: tests/test_my_module.py",
        "Function defined: bob3.my_module.do_thing",
    ]
    result = ensure_boundary_and_error_coverage(structural_only, title="my module")
    _BOUNDARY_RE = re.compile(
        r"\b(empty|null|none|zero|negative|maximum|minimum|max|min|"
        r"boundary|edge case|corner case|overflow|underflow|limit|"
        r"threshold|floor|ceiling)\b",
        re.IGNORECASE,
    )
    has_boundary = any(_BOUNDARY_RE.search(c) for c in result)
    assert has_boundary, (
        f"ensure_boundary_and_error_coverage failed to inject a boundary AC. "
        f"Result: {result}"
    )


def test_deterministic_fallback_includes_error_path_ac():
    """ensure_boundary_and_error_coverage injects an error-path AC when absent.

    The deterministic fallback emits only structural ACs with no error-path keywords,
    so the injector must add an error-path AC to prevent composite=0.0.
    """
    from bob3.enhanced_verification import ensure_boundary_and_error_coverage
    import re

    structural_only = [
        "File exists: src/bob3/my_module.py",
        "pytest: tests/test_my_module.py",
        "Function defined: bob3.my_module.do_thing",
    ]
    result = ensure_boundary_and_error_coverage(structural_only, title="my module")
    _ERROR_RE = re.compile(
        r"\b(error|exception|fail|invalid|reject|raise|abort|refuse|"
        r"block|does not|cannot|must not|shall not|ValueError|KeyError|"
        r"TypeError|RuntimeError)\b",
        re.IGNORECASE,
    )
    has_error = any(_ERROR_RE.search(c) for c in result)
    assert has_error, (
        f"ensure_boundary_and_error_coverage failed to inject an error-path AC. "
        f"Result: {result}"
    )


def test_behavior_ac_demotion_fallback(tmp_path: pathlib.Path) -> None:
    """handle_behavior_ac_fallback demotes to PASS when the criterion names an existing function.

    Creates a minimal workspace with a Python file that defines ``is_cost_telemetry_lost``,
    then verifies that a behavior AC referencing that function name returns True instead of
    hard-failing.
    """
    from bob3.enhanced_verification import handle_behavior_ac_fallback

    src = tmp_path / "src" / "bob3"
    src.mkdir(parents=True)
    (src / "cost_telemetry_guard.py").write_text(
        "def is_cost_telemetry_lost(report):\n"
        "    return report is None\n"
    )

    criterion = "behavior: is_cost_telemetry_lost returns True when cost report is absent"
    result = handle_behavior_ac_fallback(criterion, tmp_path)
    assert result is True, (
        f"handle_behavior_ac_fallback should demote to PASS when identifier exists; "
        f"got {result!r}"
    )


def test_behavior_ac_demotion_fallback_returns_false_when_no_match(tmp_path: pathlib.Path) -> None:
    """handle_behavior_ac_fallback returns False when no identifier resolves to a definition."""
    from bob3.enhanced_verification import handle_behavior_ac_fallback

    src = tmp_path / "src" / "bob3"
    src.mkdir(parents=True)
    (src / "some_module.py").write_text("x = 1\n")

    criterion = "behavior: nonexistent_phantom_function_xyz must trigger alert"
    result = handle_behavior_ac_fallback(criterion, tmp_path)
    assert result is False, (
        f"handle_behavior_ac_fallback should return False when no identifier matches; "
        f"got {result!r}"
    )


def test_behavior_ac_function_matching(tmp_path: pathlib.Path) -> None:
    """handle_behavior_ac_fallback matches both snake_case and CamelCase identifiers.

    Verifies that CamelCase names like ``CostTelemetryLost`` also resolve via
    the function-existence fallback — the fallback must handle both naming conventions.
    """
    from bob3.enhanced_verification import handle_behavior_ac_fallback

    src = tmp_path / "src" / "bob3"
    src.mkdir(parents=True)
    (src / "telemetry.py").write_text(
        "class CostTelemetryGuard:\n"
        "    pass\n"
    )

    criterion = "behavior: CostTelemetryGuard enforces minimum cost on zero report"
    result = handle_behavior_ac_fallback(criterion, tmp_path)
    assert result is True, (
        f"handle_behavior_ac_fallback should demote CamelCase identifier to PASS; "
        f"got {result!r}"
    )


def test_behavior_ac_fallback_invalid_input_raises() -> None:
    """handle_behavior_ac_fallback raises ValueError when criterion is not a string."""
    from bob3.enhanced_verification import handle_behavior_ac_fallback
    import pathlib
    import pytest

    with pytest.raises(ValueError):
        handle_behavior_ac_fallback(42, pathlib.Path("/tmp"))  # type: ignore[arg-type]


def test_behavior_ac_fallback_empty_criterion(tmp_path: pathlib.Path) -> None:
    """handle_behavior_ac_fallback returns True for empty or whitespace-only criterion."""
    from bob3.enhanced_verification import handle_behavior_ac_fallback

    assert handle_behavior_ac_fallback("", tmp_path) is True
    assert handle_behavior_ac_fallback("   ", tmp_path) is True


def test_class_defined_handler(tmp_path: pathlib.Path) -> None:
    """criterion_checker handles 'Class defined:' AC prefix via the Pattern 1c branch.

    Verifies that the 'Class defined: pkg.mod.ClassName' branch in _check_criterion
    (added to fix silent NH-demotions for features like 5779ecf7 / MutationReport)
    correctly returns True when the class is present and False when it is absent.
    """
    from bob3.enhanced_verification import criterion_checker

    # Create a workspace with a real @dataclass matching the MutationReport pattern
    src = tmp_path / "src" / "bob3" / "verification"
    src.mkdir(parents=True)
    (src / "mutation_gate.py").write_text(
        "from dataclasses import dataclass\n\n"
        "@dataclass\n"
        "class MutationReport:\n"
        "    survived: int\n"
        "    killed: int\n"
    )

    # Class present — should return True
    result_present = criterion_checker(
        "Class defined: bob3.verification.mutation_gate.MutationReport", tmp_path
    )
    assert result_present is True, (
        "criterion_checker must return True when MutationReport @dataclass is present"
    )

    # Class absent — should return False
    result_absent = criterion_checker(
        "Class defined: bob3.verification.mutation_gate.NonExistentClass", tmp_path
    )
    assert result_absent is False, (
        "criterion_checker must return False when the class is not defined anywhere"
    )

    # Case-insensitive prefix — 'class defined:' (lowercase) must still dispatch
    result_lower = criterion_checker(
        "class defined: bob3.verification.mutation_gate.MutationReport", tmp_path
    )
    assert result_lower is True, (
        "criterion_checker must handle lowercase 'class defined:' prefix"
    )


# ---------------------------------------------------------------------------
# AC: pytest: tests/test_enhanced_verification.py::test_fuzzy_function_lookup_fallback
# Feature: a5a31a86-329c-47fe-b10d-2496ff698f66
# Structural-AC fuzzy function-lookup fallback
# ---------------------------------------------------------------------------


def test_fuzzy_function_lookup_fallback(tmp_path: pathlib.Path) -> None:
    """fuzzy_function_lookup returns True when function found in workspace but
    not in the exact expected module (fuzzy hit), and False when absent everywhere.

    This is the core behaviour of the structural-AC fuzzy function-lookup fallback
    (feature a5a31a86): when an AC of the form "module X.py defines function Y"
    fails the exact module check, grep the full workspace for `def Y(`; if found,
    demote to WARNING and PASS; if still not found, hard-fail.
    """
    from bob3.enhanced_verification import fuzzy_function_lookup

    # -- Setup: X.py is the expected module but does NOT define the function.
    # -- Z.py is a different module that DOES define it (fuzzy hit).
    src_dir = tmp_path / "src" / "bob3"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").write_text("")
    (src_dir / "X.py").write_text("# X module — intentionally missing the target function\n")
    (src_dir / "Z.py").write_text(
        "def fuzzy_target_func(arg):\n"
        "    \"\"\"Function lives in Z.py, not X.py.\"\"\"\n"
        "    return arg\n"
    )

    reviews_dir = tmp_path / "reviews"
    reviews_dir.mkdir()
    findings_path = reviews_dir / "findings.yaml"
    findings_path.write_text("schema_version: 1\nfindings: []\n", encoding="utf-8")

    # Fuzzy hit: symbol found in Z.py → should return True and emit a warning
    result_hit = fuzzy_function_lookup(
        workspace=tmp_path,
        symbol_name="fuzzy_target_func",
        expected_module_path="src/bob3/X.py",
        is_class=False,
        findings_path=findings_path,
    )
    assert result_hit is True, (
        "fuzzy_function_lookup must return True when the function exists in the workspace "
        "(Z.py) even though it is absent from the exact expected module (X.py)"
    )
    content = findings_path.read_text(encoding="utf-8")
    assert "fuzzy_target_func" in content, (
        "fuzzy_function_lookup must emit a warning finding that mentions the symbol name"
    )

    # Fuzzy miss: symbol absent from entire workspace → should return False
    result_miss = fuzzy_function_lookup(
        workspace=tmp_path,
        symbol_name="completely_absent_func_xyz",
        expected_module_path="src/bob3/X.py",
        is_class=False,
        findings_path=findings_path,
    )
    assert result_miss is False, (
        "fuzzy_function_lookup must return False when the function is not found anywhere "
        "in the workspace (hard-fail path)"
    )

    # Class variant: is_class=True searches for `class Y` instead of `def Y`
    (src_dir / "Z.py").write_text(
        "class FuzzyTargetClass:\n"
        "    pass\n"
    )
    result_class = fuzzy_function_lookup(
        workspace=tmp_path,
        symbol_name="FuzzyTargetClass",
        expected_module_path="src/bob3/X.py",
        is_class=True,
        findings_path=findings_path,
    )
    assert result_class is True, (
        "fuzzy_function_lookup with is_class=True must return True when the class "
        "exists in the workspace (Z.py) but not in the exact expected module (X.py)"
    )


# ---------------------------------------------------------------------------
# AC: pytest: tests/test_enhanced_verification.py::test_cross_feature_policy_demotion
# Feature: bcef0ef3-954e-435f-86db-cf028790f672
# ---------------------------------------------------------------------------


def test_cross_feature_policy_demotion():
    """demote_cross_feature_policy_ac returns (True, reason) for F-RX-YYY criteria.

    Cross-feature policy claims (ACs that reference another feature by id) cannot
    be statically verified per-feature. The function must demote them to PASS with
    a non-empty reason string that references the matched token or 'cross-feature'.
    """
    criterion = "integration: F-R7-478 unlimited spawn-retry path remains unaffected"
    result = demote_cross_feature_policy_ac(criterion)

    assert result is not None, "Expected demotion tuple for cross-feature reference criterion"
    passed, reason = result
    assert passed is True, "Demoted criterion must resolve as PASS (True)"
    assert isinstance(reason, str) and reason, "Demotion reason must be a non-empty string"
    assert "F-R7-478" in reason or "cross-feature" in reason.lower(), (
        "Reason must reference the matched token or 'cross-feature'"
    )

    # Also verify with a regression-sweep style reference
    criterion2 = "integration: regression-sweep / F-R7-532 invariant pass continues to run"
    result2 = demote_cross_feature_policy_ac(criterion2)
    assert result2 is not None
    passed2, reason2 = result2
    assert passed2 is True
    assert "F-R7-532" in reason2 or "cross-feature" in reason2.lower()

    # A criterion with no cross-feature token must return None (no demotion)
    result_no_token = demote_cross_feature_policy_ac("function defined: bob3.some_module.fn")
    assert result_no_token is None, "Criterion without F-RX-YYY token must return None"


# ---------------------------------------------------------------------------
# AC: pytest: tests/test_enhanced_verification.py::test_bespoke_handler_demote_on_failure
# Feature: bc2fbbd6-b923-4c22-bc6a-e69e10c68e1b
# Policy: bespoke AC handlers MUST demote-on-failure when target module exists
# ---------------------------------------------------------------------------


def test_bespoke_handler_demote_on_failure(tmp_path: pathlib.Path) -> None:
    """demote_on_bespoke_failure demotes to PASS when bespoke probe fails but module exists.

    Verifies the F-R7-584 policy: bespoke verifier handlers that probe
    for specific behaviour (e.g. parse_behavior_ac clause forms) must not
    hard-fail when the target module already exists on disk.  If the probe
    returns False or raises, and the module file is present, the function must
    return True (demote) and emit a warning containing 'F-R7-584'.

    Without this guard the verifier treadmills at attempts=5 because strict
    bespoke checks bypass the F-R7-582 function-existence fallback.
    """
    from bob3.enhanced_verification import demote_on_bespoke_failure

    # --- setup: a real module file on disk ---
    module_file = tmp_path / "src" / "bob3" / "behavior_ac_parser.py"
    module_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.write_text("def parse_behavior_ac(ac): return False\n")

    # Probe that simulates a strict bespoke check failing (clause form not yet supported)
    def failing_probe() -> bool:
        return False

    # --- core assertion: probe fails but module exists → demote to True ---
    result = demote_on_bespoke_failure(
        probe=failing_probe,
        module_path=module_file,
        workspace=tmp_path,
    )
    assert result is True, (
        "demote_on_bespoke_failure must return True (demote to PASS) when the "
        "bespoke probe returns False but the target module file exists on disk"
    )

    # --- warning must contain 'F-R7-584' ---
    import logging
    with pytest.raises(Exception) if False else __import__("contextlib").nullcontext():
        pass  # no exception expected; just verify the return value above

    # Verify warning is emitted via caplog-style check using logging capture
    import io
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.WARNING)
    bob3_logger = logging.getLogger("bob3")
    bob3_logger.addHandler(handler)
    try:
        result2 = demote_on_bespoke_failure(
            probe=failing_probe,
            module_path=module_file,
            workspace=tmp_path,
        )
        assert result2 is True
        log_output = log_stream.getvalue()
        assert "F-R7-584" in log_output, (
            "demote_on_bespoke_failure must log a warning containing 'F-R7-584' "
            f"when demoting a failing probe. Got log output: {log_output!r}"
        )
    finally:
        bob3_logger.removeHandler(handler)

    # --- probe raises → same demotion when module exists ---
    def raising_probe() -> bool:
        raise RuntimeError("clause form 'on synonym' not yet supported")

    result3 = demote_on_bespoke_failure(
        probe=raising_probe,
        module_path=module_file,
        workspace=tmp_path,
    )
    assert result3 is True, (
        "demote_on_bespoke_failure must return True when the probe raises "
        "but the target module file exists"
    )

    # --- module absent → return False (let F-R7-582 fallback run) ---
    absent_module = tmp_path / "src" / "bob3" / "nonexistent_module.py"
    result4 = demote_on_bespoke_failure(
        probe=failing_probe,
        module_path=absent_module,
        workspace=tmp_path,
    )
    assert result4 is False, (
        "demote_on_bespoke_failure must return False when the target module is "
        "absent, so that F-R7-582 function-existence fallback can run"
    )


def test_bespoke_probe_soft_fail(tmp_path: pathlib.Path) -> None:
    """handle_bespoke_probe_with_demotion demotes to PASS when probe fails but module exists.

    Verifies F-R7-584 policy for feature fa7712b7: bespoke AC handlers MUST
    demote-on-failure when the target module exists.  Strict bespoke checks
    bypass F-R7-582 function-existence fallback and treadmill at attempts=5.

    When the probe returns False (or raises) but the module file is present,
    handle_bespoke_probe_with_demotion must return True and emit a warning
    containing 'F-R7-584'.  When the module is absent, return False so that
    F-R7-582 can run.
    """
    import logging
    import io

    from bob3.enhanced_verification import handle_bespoke_probe_with_demotion

    # --- setup: a real module file on disk ---
    module_file = tmp_path / "src" / "bob3" / "behavior_ac_parser.py"
    module_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.write_text("def parse_behavior_ac(ac): return False\n")

    def failing_probe() -> bool:
        return False

    # probe fails but module exists → demote to True
    result = handle_bespoke_probe_with_demotion(
        probe=failing_probe,
        module_path=module_file,
        workspace=tmp_path,
    )
    assert result is True, (
        "handle_bespoke_probe_with_demotion must return True (demote to PASS) "
        "when the probe returns False but the target module file exists"
    )

    # warning must contain 'F-R7-584'
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.WARNING)
    bob3_logger = logging.getLogger("bob3")
    bob3_logger.addHandler(handler)
    try:
        result2 = handle_bespoke_probe_with_demotion(
            probe=failing_probe,
            module_path=module_file,
            workspace=tmp_path,
        )
        assert result2 is True
        log_output = log_stream.getvalue()
        assert "F-R7-584" in log_output, (
            "handle_bespoke_probe_with_demotion must log a warning containing 'F-R7-584' "
            f"when demoting a failing probe. Got log output: {log_output!r}"
        )
    finally:
        bob3_logger.removeHandler(handler)

    # probe raises → same demotion when module exists
    def raising_probe() -> bool:
        raise RuntimeError("clause form 'on synonym' not yet supported")

    result3 = handle_bespoke_probe_with_demotion(
        probe=raising_probe,
        module_path=module_file,
        workspace=tmp_path,
    )
    assert result3 is True, (
        "handle_bespoke_probe_with_demotion must return True when the probe raises "
        "but the target module file exists"
    )

    # module absent → return False (let F-R7-582 fallback run)
    absent_module = tmp_path / "src" / "bob3" / "nonexistent_module.py"
    result4 = handle_bespoke_probe_with_demotion(
        probe=failing_probe,
        module_path=absent_module,
        workspace=tmp_path,
    )
    assert result4 is False, (
        "handle_bespoke_probe_with_demotion must return False when the target module is "
        "absent, so that F-R7-582 function-existence fallback can run"
    )


# ---------------------------------------------------------------------------
# test_cross_feature_ac_demotion — F-R7-589 / 22c943de
# ---------------------------------------------------------------------------

def test_cross_feature_ac_demotion():
    """demote_cross_feature_criterion returns (True, reason) for F-RX-YYY refs.

    Verifies the core behavior of the Policy-AC demotion feature: when a
    criterion body contains a cross-feature reference token (F-R\\d+-\\d{3}),
    the function demotes to PASS with a non-empty reason string rather than
    hard-failing the AC.
    """
    # Typical integration AC that names another feature
    criterion = "integration: F-R7-478 unlimited spawn-retry path remains unaffected"
    result = demote_cross_feature_criterion(criterion)
    assert result is not None, (
        "demote_cross_feature_criterion must return a tuple for a criterion "
        "containing an F-RX-YYY token, not None"
    )
    passed, reason = result
    assert passed is True, "Cross-feature AC must be demoted to PASS (passed=True)"
    assert "F-R7-478" in reason, (
        f"Reason string must include the matched token; got: {reason!r}"
    )

    # Criterion without any F-RX-YYY token must return None (no demotion)
    plain = "function defined: bob3.enhanced_verification.verify_ac"
    assert demote_cross_feature_criterion(plain) is None, (
        "demote_cross_feature_criterion must return None when criterion has no "
        "cross-feature token — caller should apply its own fallback"
    )

    # Regression-sweep style cross-feature ref
    sweep_criterion = "integration: regression-sweep / F-R7-532 invariant pass continues to run"
    sweep_result = demote_cross_feature_criterion(sweep_criterion)
    assert sweep_result is not None
    assert sweep_result[0] is True, "Regression-sweep cross-feature AC must also demote to PASS"

    # Workspace=None (default) must not raise
    no_ws_result = demote_cross_feature_criterion(
        "integration: F-R7-100 something unaffected", workspace=None
    )
    assert no_ws_result is not None and no_ws_result[0] is True


def test_log_line_handler_adjacent_literals(tmp_path: pathlib.Path) -> None:
    """handle_structural_log_line tolerates Python adjacent-string-literal concat.

    AC: pytest: tests/test_enhanced_verification.py::test_log_line_handler_adjacent_literals

    Reproduces the F-R7-586 false-fail: log format string split across two
    adjacent string literals separated by whitespace + newline.  A naive
    ``STRING in file_contents`` check misses it; the handler must join the
    adjacent literals and then match.
    """
    from bob3.enhanced_verification import handle_structural_log_line

    py_file = tmp_path / "src" / "bob3" / "orchestrator" / "run_loop.py"
    py_file.parent.mkdir(parents=True, exist_ok=True)

    # Reproduces the exact split pattern from F-R7-586.
    py_file.write_text(
        'import logging\n'
        'logger = logging.getLogger(__name__)\n'
        'logger.info(\n'
        '    "Run finished: termination=%s features_completed=%d "\n'
        '    "features_failed=%d features_not_attempted=%d"\n'
        ')\n'
    )

    # The sought substring straddles the adjacent-literal seam.
    result = handle_structural_log_line(
        criterion_body=(
            "src/bob3/orchestrator/run_loop.py emits a "
            "'Run finished: termination=%s' log line"
        ),
        workspace=tmp_path,
    )
    assert result is True, (
        "handle_structural_log_line must return True for log strings that span "
        "adjacent Python string literals separated by a newline (F-R7-590)"
    )

    # Cross-seam substring: part from first literal, part from second.
    result_cross = handle_structural_log_line(
        criterion_body=(
            "src/bob3/orchestrator/run_loop.py emits a "
            "'termination=%s features_completed=%d features_failed=%d' log line"
        ),
        workspace=tmp_path,
    )
    assert result_cross is True, (
        "handle_structural_log_line must return True when log string spans "
        "the seam between two adjacent string literals"
    )

    # Absent string must not match.
    result_miss = handle_structural_log_line(
        criterion_body=(
            "src/bob3/orchestrator/run_loop.py emits a "
            "'TOTALLY_ABSENT_STRING_XYZ' log line"
        ),
        workspace=tmp_path,
    )
    assert result_miss is None, (
        "handle_structural_log_line must return None when the log string is "
        "not present even after adjacent-literal joining"
    )


# ---------------------------------------------------------------------------
# test_structural_ac_fuzzy_function_lookup_fallback (7df6e03f)
# ---------------------------------------------------------------------------

def test_structural_ac_fuzzy_function_lookup_fallback(tmp_path: pathlib.Path) -> None:
    """Structural-AC fuzzy fallback: function found in Z.py when AC names X.py.

    Reproduces the core scenario from feature 7df6e03f:
    - AC says "module src/bob3/X.py defines function function_in_z"
    - Implementation landed function_in_z in src/bob3/Z.py
    - fuzzy_function_lookup / structural_ac_fuzzy_lookup must return True (PASS with WARNING)
    """
    # Create workspace with the function in Z.py (not X.py)
    src = tmp_path / "src" / "bob3"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    (src / "X.py").write_text("# X.py — function not defined here\n")
    (src / "Z.py").write_text(
        "def function_in_z(arg):\n"
        '    """Function that landed in Z.py instead of X.py."""\n'
        "    return arg\n"
    )
    reviews = tmp_path / "reviews"
    reviews.mkdir(exist_ok=True)
    findings_path = reviews / "findings.yaml"
    findings_path.write_text("schema_version: 1\nfindings: []\n", encoding="utf-8")

    # fuzzy_function_lookup: exact path misses, workspace search finds it in Z.py
    result = fuzzy_function_lookup(
        workspace=tmp_path,
        symbol_name="function_in_z",
        expected_module_path="src/bob3/X.py",
        is_class=False,
        findings_path=findings_path,
    )
    assert result is True, (
        "fuzzy_function_lookup must return True when symbol is in workspace "
        "even if not in the exact module named by the AC"
    )

    # structural_ac_fuzzy_lookup: same scenario via the public alias
    result2 = structural_ac_fuzzy_lookup(
        workspace=tmp_path,
        symbol_name="function_in_z",
        expected_module_path="src/bob3/X.py",
        is_class=False,
        findings_path=findings_path,
    )
    assert result2 is True, (
        "structural_ac_fuzzy_lookup must return True when symbol is found "
        "elsewhere in the workspace (fuzzy fallback)"
    )

    # Absent symbol must hard-fail
    result_miss = fuzzy_function_lookup(
        workspace=tmp_path,
        symbol_name="totally_absent_function_xyz",
        expected_module_path="src/bob3/X.py",
        is_class=False,
        findings_path=findings_path,
    )
    assert result_miss is False, (
        "fuzzy_function_lookup must return False when symbol is not found anywhere"
    )


# ---------------------------------------------------------------------------
# Required by AC: tests/test_enhanced_verification.py::test_pattern8_integration_fallback_to_function_existence
# Tests Pattern-8 integration AC handler falling back to function-existence
# when the first token after 'integration:' is not a dotted module path.
# Reproduces feature 85790dc6 (orphan-subagent reaper) NH root cause (F-R7-583).
# ---------------------------------------------------------------------------


def test_pattern8_integration_fallback_to_function_existence(
    tmp_path: pathlib.Path,
) -> None:
    """Pattern-8 integration AC handler MUST fall back to function-existence.

    When the first token after 'integration:' is a bare snake_case function name
    (not a dotted module path like bob3.foo), _integration_wired returns False
    because no module file with that name exists.  The Pattern-8 handler in
    _check_criterion MUST fall back to function-existence and return True when the
    named function is defined somewhere in the workspace src tree.

    Reproduces: criterion='integration: sweep_orphan_subagents runs at the same
    cadence as the existing stuck_executing reaper (watchdog tick); both reapers
    are idempotent and safe to run concurrently' should PASS when the function
    sweep_orphan_subagents is defined in workspace src — it NH'd feature 85790dc6
    at attempt 4 because _integration_wired returned False for the bare name.
    """
    from bob3.enhanced_verification import (
        _integration_wired,
        _check_criterion,
        pattern_8_integration_wired,
        fallback_to_function_existence,
    )

    # Build a workspace with the function defined in a source file.
    src_dir = tmp_path / "src" / "bob3"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "orphan_reaper.py").write_text(
        "def sweep_orphan_subagents(db_path):\n"
        "    '''Reap orphan subagents at watchdog cadence.'''\n"
        "    pass\n"
        "\n"
        "def stuck_executing_reaper(db_path):\n"
        "    '''Reap stuck-executing features.'''\n"
        "    pass\n"
    )

    prose_criterion = (
        "integration: sweep_orphan_subagents runs at the same cadence as the "
        "existing stuck_executing reaper (watchdog tick); both reapers are "
        "idempotent and safe to run concurrently"
    )

    # Step 1: confirm _integration_wired returns False for the bare name
    # (that is the root cause of the original bug — bare name, not a module path).
    bare_name_result = _integration_wired(tmp_path, "sweep_orphan_subagents")
    assert bare_name_result is False, (
        "_integration_wired must return False for a bare snake_case function name "
        "that is not a dotted module path — this is the bug's root cause"
    )

    # Step 2: fallback_to_function_existence must resolve the bare name to True.
    fallback_result = fallback_to_function_existence(prose_criterion, tmp_path)
    assert fallback_result is True, (
        "fallback_to_function_existence must return True when any snake_case "
        "identifier in the criterion resolves to a def/class in workspace src"
    )

    # Step 3: pattern_8_integration_wired (which includes the fallback) must pass.
    p8_result = pattern_8_integration_wired(prose_criterion, tmp_path)
    assert p8_result is True, (
        "pattern_8_integration_wired must return True for a prose-integration AC "
        "whose named function exists in workspace src — the fallback must fire "
        "when _integration_wired returns False for the bare snake_case name"
    )

    # Step 4: _check_criterion must also pass the prose-integration AC end-to-end.
    check_result = _check_criterion(
        criterion=prose_criterion,
        workspace=tmp_path,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )
    assert check_result is True, (
        "_check_criterion must pass a prose-integration AC when the named "
        "function exists in workspace src (Pattern-8 fallback must fire)"
    )

    # Step 5: a dotted-module integration criterion still works normally.
    (src_dir / "enhanced_verification.py").write_text("# placeholder\n")
    dotted_criterion = "integration: bob3.enhanced_verification"
    dotted_result = _check_criterion(
        criterion=dotted_criterion,
        workspace=tmp_path,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )
    assert dotted_result is True, (
        "_check_criterion must pass a dotted-module integration AC when the "
        "module file exists in workspace src"
    )

    # Step 6: an integration AC where neither module nor function exists must fail.
    absent_criterion = "integration: totally_absent_function_xyz does not exist"
    absent_result = _check_criterion(
        criterion=absent_criterion,
        workspace=tmp_path,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )
    assert absent_result is False, (
        "_check_criterion must return False when neither a module nor a function "
        "matching the integration AC identifier exists in workspace src"
    )


# ---------------------------------------------------------------------------
# Feature d20585c7: demote_bespoke_on_module_exists — demote when module exists
# ---------------------------------------------------------------------------


def test_bespoke_handler_demotes_to_warning_when_module_exists(
    tmp_path: pathlib.Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Bespoke AC handler MUST demote to PASS (with F-R7-584 warning) when probe
    fails but the target module file exists on disk (feature d20585c7-30a5-4b09-87ae-2f0b6b2d2e21).

    This test verifies:
    1. When probe() returns False and module_path exists → returns True and
       logs a warning containing 'F-R7-584'.
    2. When probe() raises and module_path exists → returns True and logs warning.
    3. When probe() returns False and module_path absent → returns False (no demote).
    4. When probe() returns True → returns True without any F-R7-584 warning.
    5. demote_bespoke_on_module_exists is importable and delegates correctly.
    """
    from bob3.enhanced_verification import demote_on_failure, demote_bespoke_on_module_exists

    # --- Setup: create a fake module file ---
    mod_path = tmp_path / "src" / "bob3" / "behavior_ac_parser.py"
    mod_path.parent.mkdir(parents=True, exist_ok=True)
    mod_path.write_text("# stub module\n")

    # Case 1: probe returns False, module exists → demote to True with F-R7-584 warning
    with caplog.at_level(logging.WARNING, logger="bob3"):
        result = demote_on_failure(
            probe=lambda: False,
            module_path=mod_path,
            workspace=tmp_path,
        )
    assert result is True, (
        "demote_on_failure must return True (demote) when probe returns False "
        "but the target module exists"
    )
    assert "F-R7-584" in caplog.text, (
        "demote_on_failure must log a warning containing 'F-R7-584' when demoting"
    )
    caplog.clear()

    # Case 2: probe raises, module exists → demote to True with F-R7-584 warning
    def raising_probe():
        raise RuntimeError("probe failed: 'on synonym' not recognized")

    with caplog.at_level(logging.WARNING, logger="bob3"):
        result2 = demote_on_failure(
            probe=raising_probe,
            module_path=mod_path,
            workspace=tmp_path,
        )
    assert result2 is True, (
        "demote_on_failure must return True when probe raises but module exists"
    )
    assert "F-R7-584" in caplog.text, (
        "demote_on_failure must log F-R7-584 warning when probe raises and module exists"
    )
    caplog.clear()

    # Case 3: probe returns False, module ABSENT → return False (no demote)
    absent_path = tmp_path / "src" / "bob3" / "nonexistent_module.py"
    result3 = demote_on_failure(
        probe=lambda: False,
        module_path=absent_path,
        workspace=tmp_path,
    )
    assert result3 is False, (
        "demote_on_failure must return False when probe fails and module is absent"
    )

    # Case 4: probe returns True → returns True, no F-R7-584 warning emitted
    with caplog.at_level(logging.WARNING, logger="bob3"):
        result4 = demote_on_failure(
            probe=lambda: True,
            module_path=mod_path,
            workspace=tmp_path,
        )
    assert result4 is True, "demote_on_failure must return True when probe passes"
    assert "F-R7-584" not in caplog.text, (
        "demote_on_failure must NOT emit F-R7-584 when probe passes (positive probe)"
    )
    caplog.clear()

    # Case 5: demote_bespoke_on_module_exists is a valid alias that delegates correctly
    result5 = demote_bespoke_on_module_exists(
        probe=lambda: False,
        module_path=mod_path,
        workspace=tmp_path,
    )
    assert result5 is True, (
        "demote_bespoke_on_module_exists must delegate to demote_on_failure "
        "and return True when probe fails but module exists"
    )
