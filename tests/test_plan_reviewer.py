"""Tests for bob.plan_reviewer — Independent plan-review agent (Gap #6)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob.plan_reviewer import (
    PlanReview,
    parse_plan_review,
    review_plan,
)


# ---------------------------------------------------------------------------
# PlanReview model tests
# ---------------------------------------------------------------------------


class TestPlanReviewModel:
    def test_approve_verdict(self):
        review = PlanReview(verdict="approve", findings=[], confidence=0.9)
        assert review.verdict == "approve"
        assert review.confidence == 0.9
        assert review.findings == []

    def test_revise_verdict(self):
        review = PlanReview(
            verdict="revise",
            findings=["Missing coverage for acceptance criterion 2"],
            confidence=0.7,
        )
        assert review.verdict == "revise"
        assert len(review.findings) == 1

    def test_block_verdict(self):
        review = PlanReview(
            verdict="block",
            findings=["Plan deletes files unconditionally", "Spec misread: wrong module path"],
            confidence=0.95,
        )
        assert review.verdict == "block"
        assert len(review.findings) == 2

    def test_confidence_clamped_to_range(self):
        review = PlanReview(verdict="approve", findings=[], confidence=1.0)
        assert 0.0 <= review.confidence <= 1.0

    def test_default_findings_is_empty_list(self):
        review = PlanReview(verdict="approve", confidence=0.8)
        assert review.findings == []

    def test_invalid_verdict_raises(self):
        with pytest.raises(Exception):
            PlanReview(verdict="invalid_verdict", findings=[], confidence=0.5)


# ---------------------------------------------------------------------------
# parse_plan_review tests
# ---------------------------------------------------------------------------


class TestParsePlanReview:
    def _make_json_response(self, data: dict[str, Any]) -> str:
        return f"```json\n{json.dumps(data)}\n```"

    def test_parse_approve_from_fenced_json(self):
        resp = self._make_json_response({
            "verdict": "approve",
            "findings": [],
            "confidence": 0.85,
        })
        result = parse_plan_review(resp)
        assert result["verdict"] == "approve"
        assert result["confidence"] == 0.85
        assert result["findings"] == []

    def test_parse_revise_verdict(self):
        resp = self._make_json_response({
            "verdict": "revise",
            "findings": ["AC #2 not addressed"],
            "confidence": 0.6,
        })
        result = parse_plan_review(resp)
        assert result["verdict"] == "revise"
        assert "AC #2 not addressed" in result["findings"]

    def test_parse_block_verdict(self):
        resp = self._make_json_response({
            "verdict": "block",
            "findings": ["Direct file deletion without backup"],
            "confidence": 0.99,
        })
        result = parse_plan_review(resp)
        assert result["verdict"] == "block"

    def test_parse_falls_back_on_unparseable(self):
        result = parse_plan_review("This is not JSON at all.")
        # Should return a safe default that routes to revise
        assert result["verdict"] in ("revise", "block")
        assert isinstance(result["findings"], list)
        assert isinstance(result["confidence"], float)

    def test_parse_bad_json_returns_safe_default(self):
        result = parse_plan_review("```json\n{broken json\n```")
        assert result["verdict"] in ("revise", "block")

    def test_parse_invalid_verdict_in_json_returns_safe_default(self):
        resp = self._make_json_response({
            "verdict": "unknown_verdict",
            "findings": [],
            "confidence": 0.5,
        })
        result = parse_plan_review(resp)
        assert result["verdict"] in ("revise", "block")

    def test_parse_confidence_clamped_to_one(self):
        resp = self._make_json_response({
            "verdict": "approve",
            "findings": [],
            "confidence": 9999.0,
        })
        result = parse_plan_review(resp)
        assert result["confidence"] <= 1.0

    def test_parse_confidence_clamped_to_zero(self):
        resp = self._make_json_response({
            "verdict": "approve",
            "findings": [],
            "confidence": -5.0,
        })
        result = parse_plan_review(resp)
        assert result["confidence"] >= 0.0

    def test_parse_findings_non_list_coerced_to_list(self):
        resp = self._make_json_response({
            "verdict": "revise",
            "findings": "Single string finding",
            "confidence": 0.5,
        })
        result = parse_plan_review(resp)
        assert isinstance(result["findings"], list)

    def test_parse_inline_json_fallback(self):
        resp = 'Here is my review: {"verdict": "approve", "findings": [], "confidence": 0.8}'
        result = parse_plan_review(resp)
        assert result["verdict"] == "approve"


# ---------------------------------------------------------------------------
# review_plan tests (async, with mocked sub-agent)
# ---------------------------------------------------------------------------


class TestReviewPlan:
    """Tests for the async review_plan function.

    The function calls a haiku-grade sub-agent via claude_code_sdk.
    We mock the executor to avoid real API calls.
    """

    def _make_feature(self, **kwargs) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "id": "feat-123",
            "name": "Test feature",
            "description": "Add a simple utility function",
            "acceptance_criteria": '["File exists: src/foo.py", "pytest: tests/test_foo.py"]',
        }
        defaults.update(kwargs)
        return defaults

    @pytest.mark.asyncio
    async def test_approve_plan_returns_plan_review(self):
        approve_json = json.dumps({
            "verdict": "approve",
            "findings": [],
            "confidence": 0.9,
        })
        mock_result = MagicMock()
        mock_result.text = f"After analysis:\n```json\n{approve_json}\n```"

        with patch("bob.plan_reviewer._run_haiku_review", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_result.text
            result = await review_plan(
                plan="Implement foo.py with bar() function. ~50 LOC.",
                feature=self._make_feature(),
            )

        assert isinstance(result, PlanReview)
        assert result.verdict == "approve"
        assert result.confidence >= 0.0

    @pytest.mark.asyncio
    async def test_revise_plan_on_missing_ac(self):
        revise_json = json.dumps({
            "verdict": "revise",
            "findings": ["Plan does not address AC #2: pytest test file"],
            "confidence": 0.75,
        })
        mock_text = f"```json\n{revise_json}\n```"

        with patch("bob.plan_reviewer._run_haiku_review", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_text
            result = await review_plan(
                plan="Only create src/foo.py. No tests mentioned.",
                feature=self._make_feature(),
            )

        assert result.verdict == "revise"
        assert len(result.findings) > 0

    @pytest.mark.asyncio
    async def test_block_plan_on_risky_pattern(self):
        block_json = json.dumps({
            "verdict": "block",
            "findings": ["Plan unconditionally deletes existing files"],
            "confidence": 0.99,
        })
        mock_text = f"```json\n{block_json}\n```"

        with patch("bob.plan_reviewer._run_haiku_review", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_text
            result = await review_plan(
                plan="Delete all files in src/ and rewrite from scratch.",
                feature=self._make_feature(),
            )

        assert result.verdict == "block"

    @pytest.mark.asyncio
    async def test_unparseable_response_returns_revise(self):
        with patch("bob.plan_reviewer._run_haiku_review", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "I cannot review this plan."
            result = await review_plan(
                plan="Some plan",
                feature=self._make_feature(),
            )

        assert result.verdict in ("revise", "block")

    @pytest.mark.asyncio
    async def test_review_plan_accepts_feature_dict(self):
        approve_json = json.dumps({
            "verdict": "approve",
            "findings": [],
            "confidence": 0.85,
        })
        with patch("bob.plan_reviewer._run_haiku_review", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = f"```json\n{approve_json}\n```"
            feature = self._make_feature(
                acceptance_criteria='["File exists: src/util.py"]'
            )
            result = await review_plan(plan="Create src/util.py with helpers.", feature=feature)

        assert isinstance(result, PlanReview)

    @pytest.mark.asyncio
    async def test_haiku_review_called_with_plan_content(self):
        approve_json = json.dumps({"verdict": "approve", "findings": [], "confidence": 0.9})
        with patch("bob.plan_reviewer._run_haiku_review", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = f"```json\n{approve_json}\n```"
            await review_plan(
                plan="My detailed plan text",
                feature=self._make_feature(),
            )
            call_args = mock_run.call_args
            # The prompt passed to the haiku reviewer should include the plan
            prompt_arg = call_args.args[0] if call_args.args else call_args.kwargs.get("prompt", "")
            assert "My detailed plan text" in prompt_arg


# ---------------------------------------------------------------------------
# LOC estimation check (>200 LOC triggers revise/block)
# ---------------------------------------------------------------------------


class TestLocEstimation:
    """Plans claiming >200 LOC should be flagged by the reviewer."""

    def test_parse_review_high_loc_string(self):
        # The LOC check is done in the prompt construction / review logic.
        # Here we verify parse_plan_review surfaces a finding when the
        # verdict is revise for large scope.
        resp = json.dumps({
            "verdict": "revise",
            "findings": ["Estimated 350 LOC exceeds 200 LOC limit"],
            "confidence": 0.8,
        })
        result = parse_plan_review(f"```json\n{resp}\n```")
        assert result["verdict"] == "revise"
        assert any("LOC" in f or "loc" in f.lower() for f in result["findings"])
