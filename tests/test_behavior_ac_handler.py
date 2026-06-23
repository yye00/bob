"""Tests for bob3.behavior_ac_handler.

Covers:
  - extract_quoted_literals: extracts MUST-mention / MUST-NOT-use pairs
  - verify_substring_presence: checks literals against workspace .py files
  - verify_behavior_ac_quoted_substring: end-to-end AC verification
"""

from __future__ import annotations

import pathlib

import pytest

from bob3.behavior_ac_handler import (
    extract_quoted_literals,
    verify_substring_presence,
    verify_behavior_ac_quoted_substring,
)


# ---------------------------------------------------------------------------
# extract_quoted_literals
# ---------------------------------------------------------------------------

class TestExtractQuotedLiterals:
    def test_both_clauses(self):
        criterion = "MUST mention 'Queue drained' and MUST NOT use the phrase 'All remaining features are blocked'"
        must_mention, must_not_use = extract_quoted_literals(criterion)
        assert must_mention == "Queue drained"
        assert must_not_use == "All remaining features are blocked"

    def test_must_mention_only(self):
        must_mention, must_not_use = extract_quoted_literals("MUST mention 'hello'")
        assert must_mention == "hello"
        assert must_not_use is None

    def test_must_not_use_only(self):
        must_mention, must_not_use = extract_quoted_literals("MUST NOT use 'bad_string'")
        assert must_mention is None
        assert must_not_use == "bad_string"

    def test_no_literals(self):
        must_mention, must_not_use = extract_quoted_literals("behavior: system exits cleanly")
        assert must_mention is None
        assert must_not_use is None

    def test_empty_string(self):
        must_mention, must_not_use = extract_quoted_literals("")
        assert must_mention is None
        assert must_not_use is None

    def test_case_insensitive_must(self):
        must_mention, must_not_use = extract_quoted_literals("must mention 'token'")
        assert must_mention == "token"

    def test_double_quotes(self):
        must_mention, must_not_use = extract_quoted_literals('MUST mention "value"')
        assert must_mention == "value"

    def test_full_behavior_ac(self):
        criterion = (
            "behavior: the CLI termination message for ALL_BLOCKED "
            "MUST mention 'Queue drained' and "
            "MUST NOT use the phrase 'All remaining features are blocked'"
        )
        must_mention, must_not_use = extract_quoted_literals(criterion)
        assert must_mention == "Queue drained"
        assert must_not_use == "All remaining features are blocked"


# ---------------------------------------------------------------------------
# verify_substring_presence
# ---------------------------------------------------------------------------

class TestVerifySubstringPresence:
    def test_both_none_returns_none(self, tmp_path):
        result = verify_substring_presence(None, None, tmp_path)
        assert result is None

    def test_must_mention_found_no_forbid(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "cli.py").write_text("Queue drained\n")
        result = verify_substring_presence("Queue drained", None, tmp_path)
        assert result is True

    def test_must_mention_not_found_returns_none(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "cli.py").write_text("goodbye\n")
        result = verify_substring_presence("Queue drained", None, tmp_path)
        assert result is None

    def test_forbid_absent_returns_true(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "cli.py").write_text("Queue drained\n")
        result = verify_substring_presence(None, "forbidden phrase", tmp_path)
        assert result is True

    def test_forbid_present_returns_none(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "cli.py").write_text("forbidden phrase\n")
        result = verify_substring_presence(None, "forbidden phrase", tmp_path)
        assert result is None

    def test_mention_found_forbid_absent_returns_true(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "cli.py").write_text("Queue drained\n")
        result = verify_substring_presence("Queue drained", "forbidden phrase", tmp_path)
        assert result is True

    def test_mention_found_forbid_present_returns_none(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "cli.py").write_text("Queue drained and forbidden phrase\n")
        result = verify_substring_presence("Queue drained", "forbidden phrase", tmp_path)
        assert result is None

    def test_no_src_dir_mention_returns_none(self, tmp_path):
        result = verify_substring_presence("some string", None, tmp_path)
        assert result is None

    def test_no_src_dir_forbid_returns_true(self, tmp_path):
        result = verify_substring_presence(None, "forbidden", tmp_path)
        assert result is True

    def test_nested_py_files(self, tmp_path):
        src = tmp_path / "src"
        (src / "sub").mkdir(parents=True)
        (src / "sub" / "deep.py").write_text("Queue drained\n")
        result = verify_substring_presence("Queue drained", None, tmp_path)
        assert result is True


# ---------------------------------------------------------------------------
# verify_behavior_ac_quoted_substring — integration
# ---------------------------------------------------------------------------

class TestVerifyBehaviorAcQuotedSubstring:
    def test_valid_ac_pass(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "cli.py").write_text("Queue drained\n")
        criterion = "MUST mention 'Queue drained' and MUST NOT use the phrase 'deprecated call'"
        result = verify_behavior_ac_quoted_substring(criterion, tmp_path)
        assert result is True

    def test_no_literals_returns_none(self, tmp_path):
        result = verify_behavior_ac_quoted_substring("behavior: exits cleanly", tmp_path)
        assert result is None

    def test_non_str_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="str"):
            verify_behavior_ac_quoted_substring(None, tmp_path)

    def test_int_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            verify_behavior_ac_quoted_substring(42, tmp_path)

    def test_empty_string_returns_none(self, tmp_path):
        result = verify_behavior_ac_quoted_substring("", tmp_path)
        assert result is None

    def test_full_behavior_ac_match(self, tmp_path):
        """The motivating use case: F-R7-586 ALL_BLOCKED rename verification."""
        src = tmp_path / "src"
        (src / "bob3" / "cli").mkdir(parents=True)
        (src / "bob3" / "cli" / "__init__.py").write_text(
            "# CLI\n"
            "print('Queue drained')\n"
        )
        criterion = (
            "behavior: the CLI termination message for ALL_BLOCKED "
            "MUST mention 'Queue drained' and "
            "MUST NOT use the phrase 'All remaining features are blocked'"
        )
        result = verify_behavior_ac_quoted_substring(criterion, tmp_path)
        assert result is True

    def test_forbidden_phrase_present_fails(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "cli.py").write_text(
            "Queue drained\nAll remaining features are blocked\n"
        )
        criterion = (
            "MUST mention 'Queue drained' and "
            "MUST NOT use the phrase 'All remaining features are blocked'"
        )
        result = verify_behavior_ac_quoted_substring(criterion, tmp_path)
        assert result is None
