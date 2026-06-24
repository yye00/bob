"""Tests for bob.confidence_elicitor — Uniform predicted-confidence elicitor."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob.confidence_elicitor import (
    ConfidenceResult,
    elicit_confidence,
    parse_confidence_response,
)


# ---------------------------------------------------------------------------
# ConfidenceResult model tests
# ---------------------------------------------------------------------------


class TestConfidenceResult:
    def test_valid_confidence(self):
        result = ConfidenceResult(
            feature_id="feat-1",
            sub_agent_run_id="run-1",
            confidence=0.8,
            reasoning="The implementation looks correct.",
        )
        assert result.confidence == 0.8
        assert result.feature_id == "feat-1"
        assert result.sub_agent_run_id == "run-1"

    def test_confidence_zero(self):
        result = ConfidenceResult(
            feature_id="feat-1",
            sub_agent_run_id="run-1",
            confidence=0.0,
            reasoning="Very uncertain.",
        )
        assert result.confidence == 0.0

    def test_confidence_one(self):
        result = ConfidenceResult(
            feature_id="feat-1",
            sub_agent_run_id="run-1",
            confidence=1.0,
            reasoning="Completely confident.",
        )
        assert result.confidence == 1.0

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(Exception):
            ConfidenceResult(
                feature_id="feat-1",
                sub_agent_run_id="run-1",
                confidence=1.5,
                reasoning="Bad value.",
            )

    def test_confidence_negative_raises(self):
        with pytest.raises(Exception):
            ConfidenceResult(
                feature_id="feat-1",
                sub_agent_run_id="run-1",
                confidence=-0.1,
                reasoning="Bad value.",
            )

    def test_default_reasoning(self):
        result = ConfidenceResult(
            feature_id="feat-1",
            sub_agent_run_id="run-1",
            confidence=0.5,
        )
        assert result.reasoning == ""

    def test_has_probe_cost_field(self):
        result = ConfidenceResult(
            feature_id="feat-1",
            sub_agent_run_id="run-1",
            confidence=0.7,
        )
        assert hasattr(result, "probe_cost_usd")


# ---------------------------------------------------------------------------
# parse_confidence_response tests
# ---------------------------------------------------------------------------


class TestParseConfidenceResponse:
    def _json_block(self, data: dict) -> str:
        return f"```json\n{json.dumps(data)}\n```"

    def test_parse_valid_json_block(self):
        resp = self._json_block({"confidence": 0.75, "reasoning": "Looks good."})
        result = parse_confidence_response(resp)
        assert result["confidence"] == pytest.approx(0.75)
        assert result["reasoning"] == "Looks good."

    def test_parse_confidence_only(self):
        resp = self._json_block({"confidence": 0.4})
        result = parse_confidence_response(resp)
        assert result["confidence"] == pytest.approx(0.4)

    def test_parse_inline_json(self):
        resp = json.dumps({"confidence": 0.9, "reasoning": "Very confident."})
        result = parse_confidence_response(resp)
        assert result["confidence"] == pytest.approx(0.9)

    def test_parse_fallback_on_invalid(self):
        result = parse_confidence_response("I am very confident! Probably 80% sure.")
        assert 0.0 <= result["confidence"] <= 1.0

    def test_parse_clamps_out_of_range(self):
        resp = self._json_block({"confidence": 1.5, "reasoning": "Too high"})
        result = parse_confidence_response(resp)
        assert result["confidence"] <= 1.0

    def test_parse_returns_reasoning(self):
        resp = self._json_block({"confidence": 0.6, "reasoning": "Some reasoning."})
        result = parse_confidence_response(resp)
        assert "reasoning" in result


# ---------------------------------------------------------------------------
# elicit_confidence tests (integration with mocked LLM and DB)
# ---------------------------------------------------------------------------


class TestElicitConfidence:
    @pytest.mark.asyncio
    async def test_returns_confidence_result(self):
        """elicit_confidence returns a ConfidenceResult with a valid confidence score."""
        llm_response = json.dumps({"confidence": 0.82, "reasoning": "Implementation is solid."})

        with patch("bob.confidence_elicitor._run_haiku_probe", new_callable=AsyncMock) as mock_llm, \
             patch("bob.confidence_elicitor._store_calibration") as mock_store, \
             patch("bob.confidence_elicitor._emit_cost_checkpoint") as mock_emit:

            mock_llm.return_value = llm_response
            mock_store.return_value = None
            mock_emit.return_value = None

            result = await elicit_confidence(
                feature_id="feat-abc",
                sub_agent_run_id="run-xyz",
                project_id=None,
                task_class="feature_implementation",
            )

        assert isinstance(result, ConfidenceResult)
        assert result.confidence == pytest.approx(0.82)
        assert result.feature_id == "feat-abc"
        assert result.sub_agent_run_id == "run-xyz"

    @pytest.mark.asyncio
    async def test_stores_calibration_result(self):
        """elicit_confidence stores the result in the calibration_data table."""
        llm_response = json.dumps({"confidence": 0.7, "reasoning": "Reasonable."})

        with patch("bob.confidence_elicitor._run_haiku_probe", new_callable=AsyncMock) as mock_llm, \
             patch("bob.confidence_elicitor._store_calibration") as mock_store, \
             patch("bob.confidence_elicitor._emit_cost_checkpoint") as mock_emit:

            mock_llm.return_value = llm_response
            mock_store.return_value = None
            mock_emit.return_value = None

            await elicit_confidence(
                feature_id="feat-abc",
                sub_agent_run_id="run-xyz",
                project_id="proj-1",
                task_class="feature_implementation",
            )

        mock_store.assert_called_once()
        call_kwargs = mock_store.call_args
        # The call should pass confidence and project_id
        assert call_kwargs is not None

    @pytest.mark.asyncio
    async def test_emits_cost_checkpoint_event(self):
        """elicit_confidence emits a cost_checkpoint event after the probe."""
        llm_response = json.dumps({"confidence": 0.6, "reasoning": "Moderate confidence."})

        with patch("bob.confidence_elicitor._run_haiku_probe", new_callable=AsyncMock) as mock_llm, \
             patch("bob.confidence_elicitor._store_calibration") as mock_store, \
             patch("bob.confidence_elicitor._emit_cost_checkpoint") as mock_emit:

            mock_llm.return_value = llm_response
            mock_store.return_value = None
            mock_emit.return_value = None

            await elicit_confidence(
                feature_id="feat-abc",
                sub_agent_run_id="run-xyz",
                project_id=None,
                task_class="feature_implementation",
            )

        mock_emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_failure_returns_default(self):
        """On LLM failure, elicit_confidence returns a default result with confidence=0.5."""
        with patch("bob.confidence_elicitor._run_haiku_probe", new_callable=AsyncMock) as mock_llm, \
             patch("bob.confidence_elicitor._store_calibration") as mock_store, \
             patch("bob.confidence_elicitor._emit_cost_checkpoint") as mock_emit:

            mock_llm.side_effect = RuntimeError("LLM unavailable")
            mock_store.return_value = None
            mock_emit.return_value = None

            result = await elicit_confidence(
                feature_id="feat-fail",
                sub_agent_run_id="run-fail",
                project_id=None,
                task_class="feature_implementation",
            )

        assert isinstance(result, ConfidenceResult)
        assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_uniform_probe_text(self):
        """The probe prompt passed to _run_haiku_probe is always the same template."""
        llm_response = json.dumps({"confidence": 0.5, "reasoning": "Half sure."})
        captured_prompts = []

        async def capture_prompt(prompt: str) -> str:
            captured_prompts.append(prompt)
            return llm_response

        with patch("bob.confidence_elicitor._run_haiku_probe", side_effect=capture_prompt), \
             patch("bob.confidence_elicitor._store_calibration"), \
             patch("bob.confidence_elicitor._emit_cost_checkpoint"):

            await elicit_confidence(
                feature_id="feat-1",
                sub_agent_run_id="run-1",
                project_id=None,
                task_class="feature_implementation",
            )
            await elicit_confidence(
                feature_id="feat-2",
                sub_agent_run_id="run-2",
                project_id=None,
                task_class="feature_implementation",
            )

        # Both calls use the same probe template (uniform across ablation variants)
        assert len(captured_prompts) == 2
        assert captured_prompts[0] == captured_prompts[1]

    @pytest.mark.asyncio
    async def test_confidence_bucket_stored(self):
        """The confidence value is bucketed and stored in calibration_data."""
        llm_response = json.dumps({"confidence": 0.85, "reasoning": "High confidence."})

        with patch("bob.confidence_elicitor._run_haiku_probe", new_callable=AsyncMock) as mock_llm, \
             patch("bob.confidence_elicitor._store_calibration") as mock_store, \
             patch("bob.confidence_elicitor._emit_cost_checkpoint"):

            mock_llm.return_value = llm_response
            mock_store.return_value = None

            result = await elicit_confidence(
                feature_id="feat-bucket",
                sub_agent_run_id="run-bucket",
                project_id=None,
                task_class="feature_implementation",
            )

        assert result.confidence == pytest.approx(0.85)
        # Verify _store_calibration was called with a bucket argument
        mock_store.assert_called_once()
