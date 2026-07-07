"""F-R7-607 classifier-precedence-hoist tests.

AC: pytest: tests/test_r7_607_classifier_precedence_hoist.py
AC: Function defined: bob.run_loop.classify_mcp_transient_pre_hook
AC: integration: bob.run_loop

Verifies that classify_mcp_transient_pre_hook (bob.run_loop) fires the
F-R7-597 MCP-transient classifier BEFORE the "blocked by git hook rejection;
needs human review" demotion path. When any MCP-transient token matches the
captured evaluator stderr, the classifier must signal intercept=True so the
caller resets the feature to 'ready' and SKIPS the git-hook-rejection emit —
subject to the same 5-retry cap as F-R7-597.
"""

from __future__ import annotations

import json
import logging

import pytest

from bob import run_loop
from bob.run_loop import (
    classify_mcp_transient,
    classify_mcp_transient_pre_hook,
    drain_mcp_transient_summary,
)


class TestFunctionDefined:
    """AC: Function defined: bob.run_loop.classify_mcp_transient_pre_hook."""

    def test_callable(self) -> None:
        assert callable(classify_mcp_transient_pre_hook)

    def test_delegates_to_classify_mcp_transient(self) -> None:
        stderr = "self signed certificate in certificate chain"
        hoist = classify_mcp_transient_pre_hook(stderr=stderr, retry_count=0)
        direct = classify_mcp_transient(stderr=stderr, retry_count=0)
        assert hoist == direct


class TestFullTokenSetIntercepts:
    """Each F-R7-597 token in the description must trigger the pre-hook intercept."""

    @pytest.mark.parametrize("stderr", [
        "self signed certificate in certificate chain",
        "TLS: self-signed certificate rejected",
        "MCP server: Connection failed after retries",
        "HTTP Connection failed to endpoint",
        "Streamable HTTP error while contacting server",
        "Server rejected the configured Authorization header",
        "MCP server responded 403 Forbidden",
    ])
    def test_transient_token_intercepts(self, stderr: str) -> None:
        result = classify_mcp_transient_pre_hook(stderr=stderr, retry_count=0)
        assert result["intercept"] is True
        assert result["matched_token"]
        assert result["event"] == "EVALUATOR_MCP_TRANSIENT_PRE_HOOK"


class TestGitHookRejectionScenario:
    """The exact 6176b430 scenario: evaluator stderr carries the full token set."""

    STDERR = (
        "Streamable HTTP error\n"
        "self signed certificate in certificate chain\n"
        "MCP server: Connection failed\n"
        "Server rejected the configured Authorization header\n"
        "verdict=INSUFFICIENT_EVIDENCE\n"
        "blocked by git hook rejection; needs human review\n"
    )

    def test_pre_hook_intercepts_before_demotion(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=self.STDERR, retry_count=0, feature_id="6176b430"
        )
        assert result["intercept"] is True, (
            "MCP-transient classifier must fire even when the git-hook-rejection "
            "phrase is also present in stderr"
        )

    def test_feature_id_echoed(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=self.STDERR, retry_count=0, feature_id="6176b430"
        )
        assert result["feature_id"] == "6176b430"

    def test_more_specific_token_matched_first(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr=self.STDERR, retry_count=0
        )
        assert result["matched_token"] == "self signed certificate in certificate chain"


class TestPlainGitHookRejectionNotIntercepted:
    """A pure git-hook-rejection (no MCP tokens) must NOT be intercepted."""

    def test_plain_hook_rejection_passes_through(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="blocked by git hook rejection; needs human review",
            retry_count=0,
        )
        assert result["intercept"] is False
        assert result["matched_token"] is None


class TestRetryCapPrecedence:
    """The pre-hook obeys the same 5-retry cap as F-R7-597."""

    def test_below_cap_intercepts(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="self signed certificate in certificate chain",
            retry_count=4,
        )
        assert result["intercept"] is True

    def test_at_cap_falls_through_to_demotion(self) -> None:
        result = classify_mcp_transient_pre_hook(
            stderr="self signed certificate in certificate chain",
            retry_count=5,
        )
        assert result["intercept"] is False

    def test_cap_matches_module_constant(self) -> None:
        assert run_loop._MCP_TRANSIENT_RETRY_CAP == 5


class TestTelemetrySummary:
    """PRE_HOOK_TRANSIENT_SUMMARY telemetry on drain."""

    def test_summary_shape(self) -> None:
        summary = drain_mcp_transient_summary(intercepted=3)
        assert summary == {
            "event": "PRE_HOOK_TRANSIENT_SUMMARY",
            "intercepted": 3,
        }

    def test_summary_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger=run_loop.logger.name):
            drain_mcp_transient_summary(intercepted=7)
        events = [
            json.loads(r.message)
            for r in caplog.records
            if r.message.strip().startswith("{")
        ]
        summaries = [e for e in events if e.get("event") == "PRE_HOOK_TRANSIENT_SUMMARY"]
        assert summaries
        assert summaries[-1]["intercepted"] == 7


class TestInterceptLogsEvent:
    """A firing intercept emits the EVALUATOR_MCP_TRANSIENT_PRE_HOOK log event."""

    def test_event_emitted_on_intercept(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger=run_loop.logger.name):
            classify_mcp_transient_pre_hook(
                stderr="Streamable HTTP error",
                retry_count=0,
                feature_id="abc123",
            )
        events = [
            json.loads(r.message)
            for r in caplog.records
            if r.message.strip().startswith("{")
        ]
        hits = [e for e in events if e.get("event") == "EVALUATOR_MCP_TRANSIENT_PRE_HOOK"]
        assert hits
        assert hits[-1]["feature_id"] == "abc123"


class TestIntegrationModuleSurface:
    """AC: integration: bob.run_loop — required symbols are importable/present."""

    def test_module_exposes_pre_hook(self) -> None:
        assert hasattr(run_loop, "classify_mcp_transient_pre_hook")

    def test_module_exposes_classifier(self) -> None:
        assert hasattr(run_loop, "classify_mcp_transient")

    def test_module_exposes_drain(self) -> None:
        assert hasattr(run_loop, "drain_mcp_transient_summary")

    def test_token_set_present(self) -> None:
        assert run_loop._MCP_TRANSIENT_TOKENS
