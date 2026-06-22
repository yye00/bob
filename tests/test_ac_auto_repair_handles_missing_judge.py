"""Tests that handle_missing_judge raises EquivalenceJudgeUnavailableError when LLM is unreachable."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from bob3.spec_quality.ac_auto_repair import (
    EquivalenceJudgeUnavailableError,
    handle_missing_judge,
)

_ORIGINAL = "The system shall process all requests within 200ms."
_REWRITE = "The system shall handle all requests in under 200 milliseconds."


class TestHandleMissingJudge:
    """handle_missing_judge must raise EquivalenceJudgeUnavailableError when judge LLM fails."""

    def test_raises_when_llm_call_fails(self) -> None:
        with patch(
            "bob3.spec_quality.ac_auto_repair._call_llm_judge",
            side_effect=ConnectionError("service unavailable"),
        ):
            with pytest.raises(EquivalenceJudgeUnavailableError) as exc_info:
                handle_missing_judge(_ORIGINAL, _REWRITE)

        assert "judge" in str(exc_info.value).lower()

    def test_error_message_contains_judge(self) -> None:
        with patch(
            "bob3.spec_quality.ac_auto_repair._call_llm_judge",
            side_effect=TimeoutError("timed out"),
        ):
            with pytest.raises(EquivalenceJudgeUnavailableError) as exc_info:
                handle_missing_judge(_ORIGINAL, _REWRITE)

        assert "judge" in str(exc_info.value).lower()

    def test_raises_on_import_error(self) -> None:
        with patch(
            "bob3.spec_quality.ac_auto_repair._call_llm_judge",
            side_effect=ImportError("anthropic not installed"),
        ):
            with pytest.raises(EquivalenceJudgeUnavailableError):
                handle_missing_judge(_ORIGINAL, _REWRITE)

    def test_returns_true_when_judge_says_equivalent(self) -> None:
        mock_response = type(
            "Resp",
            (),
            {"content": [type("C", (), {"text": "EQUIVALENT: true\nRATIONALE: Same constraint."})()]},
        )()
        with patch(
            "bob3.spec_quality.ac_auto_repair._call_llm_judge",
            return_value=mock_response,
        ):
            is_equiv, rationale = handle_missing_judge(_ORIGINAL, _REWRITE)

        assert is_equiv is True
        assert rationale

    def test_returns_false_when_judge_says_not_equivalent(self) -> None:
        mock_response = type(
            "Resp",
            (),
            {"content": [type("C", (), {"text": "EQUIVALENT: false\nRATIONALE: Different constraint."})()]},
        )()
        with patch(
            "bob3.spec_quality.ac_auto_repair._call_llm_judge",
            return_value=mock_response,
        ):
            is_equiv, _ = handle_missing_judge(_ORIGINAL, _REWRITE)

        assert is_equiv is False
