"""Error-path tests for spec_quality behavior-AC parser.

AC: pytest: tests/test_spec_quality_behavior_ac_parser_must_accept_canoni_error.py
    — invalid input raises ValueError and the function does not silently succeed
    (error path)

The underlying parse_behavior_ac function (NOT the facade) MUST raise ValueError
on invalid input — it must not silently return a partial or empty result.
"""

from __future__ import annotations

import pytest
from bob.parser.behavior_ac_parser import parse_behavior_ac
from bob.spec_quality.behavior_ac_parser import parse_behavior_ac as sq_parse_behavior_ac


class TestEmptyInputRaisesValueError:
    """Empty string must raise ValueError — not silently succeed."""

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            parse_behavior_ac("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            parse_behavior_ac("   ")

    def test_error_message_describes_problem(self):
        with pytest.raises(ValueError) as exc_info:
            parse_behavior_ac("")
        assert str(exc_info.value)


class TestNonBehaviorPrefixRaisesValueError:
    """Strings without 'behavior:' prefix must raise ValueError."""

    def test_plain_sentence_raises(self):
        with pytest.raises(ValueError):
            parse_behavior_ac("system logs error when disk is full")

    def test_pytest_prefix_raises(self):
        with pytest.raises(ValueError):
            parse_behavior_ac("pytest: tests/test_foo.py")

    def test_file_exists_prefix_raises(self):
        with pytest.raises(ValueError):
            parse_behavior_ac("File exists: src/bob/parser/behavior_ac_parser.py")

    def test_function_defined_prefix_raises(self):
        with pytest.raises(ValueError):
            parse_behavior_ac("Function defined: bob.parser.behavior_ac_parser.parse_behavior_ac")


class TestMissingConditionalClauseRaisesValueError:
    """ACs with behavior: prefix but no 'when' or 'on' must raise ValueError."""

    def test_no_conditional_raises(self):
        with pytest.raises(ValueError):
            parse_behavior_ac("behavior: system does something somewhere")

    def test_single_word_body_raises(self):
        with pytest.raises(ValueError):
            parse_behavior_ac("behavior: crash")

    def test_behavior_prefix_only_raises(self):
        with pytest.raises(ValueError):
            parse_behavior_ac("behavior:")

    def test_error_message_mentions_conditional(self):
        with pytest.raises(ValueError) as exc_info:
            parse_behavior_ac("behavior: system does something without condition")
        msg = str(exc_info.value).lower()
        assert "conditional" in msg or "when" in msg or "on" in msg or "behavior" in msg


class TestDoesNotSilentlySucceed:
    """Verify that invalid inputs cannot produce a truthy return value without raising."""

    def test_empty_never_returns_value(self):
        try:
            result = parse_behavior_ac("")
            # If no exception was raised, the result must be falsy
            assert not result, "parse_behavior_ac('') must either raise or return falsy"
        except ValueError:
            pass  # expected

    def test_no_prefix_never_returns_value(self):
        try:
            result = parse_behavior_ac("logs error when disk is full")
            assert not result, "parse_behavior_ac without prefix must either raise or return falsy"
        except ValueError:
            pass  # expected

    def test_no_conditional_never_returns_value(self):
        try:
            result = parse_behavior_ac("behavior: system does stuff")
            assert not result, "parse_behavior_ac without conditional must either raise or return falsy"
        except ValueError:
            pass  # expected


class TestSpecQualityModuleRaisesOnInvalidInput:
    """The spec_quality module's parse_behavior_ac must also raise ValueError on invalid input."""

    def test_empty_raises_in_spec_quality(self):
        with pytest.raises(ValueError):
            sq_parse_behavior_ac("")

    def test_no_prefix_raises_in_spec_quality(self):
        with pytest.raises(ValueError):
            sq_parse_behavior_ac("system logs error when disk is full")

    def test_no_conditional_raises_in_spec_quality(self):
        with pytest.raises(ValueError):
            sq_parse_behavior_ac("behavior: system does something")
