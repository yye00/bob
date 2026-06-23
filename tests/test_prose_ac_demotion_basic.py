"""Basic tests for prose_ac_demotion module (F-R7-576)."""

from __future__ import annotations

import json
import logging

import pytest

from bob3.verification.prose_ac_demotion import (
    demote_prose_ac,
    is_executable_or_structural_criterion,
    log_prose_ac_demoted,
)


# ---------------------------------------------------------------------------
# is_executable_or_structural_criterion
# ---------------------------------------------------------------------------

class TestIsExecutableOrStructuralCriterion:
    """Verify marker recognition for every documented prefix."""

    @pytest.mark.parametrize("criterion", [
        "pytest: tests/foo.py",
        "Pytest: tests/bar.py",
        "PYTEST: tests/baz.py",
        "python: assert 1 == 1",
        "CI tests: 5 golden specs",
        "forbidden_imports: os.system",
        "behavioral_signature: command=./bin/app",
        "deterministic_output: command=./run.sh",
        "resource_limit: memory=128MB",
        "test_coupling: true",
        "mms: 0.95",
        "conserves: energy",
        "File exists: src/bob3/foo.py",
        "File exist: src/bob3/bar.py",
        "Function defined: bob3.foo.bar",
        "Class defined: bob3.Foo",
        "function implemented by baz()",
        "method implemented in quux()",
        "integration: bob3.orchestrator.stuck_executing_reaper",
        "cmake build succeeds",
        "no compilation errors in module",
        "no errors raised",
    ])
    def test_structural_markers_return_true(self, criterion: str) -> None:
        assert is_executable_or_structural_criterion(criterion) is True

    def test_prose_criterion_returns_false(self) -> None:
        criterion = "EVERY sub-agent routes through spawn_with_retry"
        assert is_executable_or_structural_criterion(criterion) is False

    def test_b6873bac_prose_pattern_returns_false(self) -> None:
        criterion = (
            "EVERY Claude-CLI sub-agent invocation in the codebase routes through "
            "spawn_with_retry — grep guard: no remaining direct `claude --` subprocess "
            "calls outside spawn_retry.py"
        )
        assert is_executable_or_structural_criterion(criterion) is False

    def test_transient_retries_prose_returns_false(self) -> None:
        criterion = (
            "Transient retries do NOT increment refinement_attempts, "
            "bootstrap_attempts, verification_failures, or research_iterations "
            "in any pipeline stage"
        )
        assert is_executable_or_structural_criterion(criterion) is False

    def test_empty_string_returns_false(self) -> None:
        assert is_executable_or_structural_criterion("") is False


# ---------------------------------------------------------------------------
# demote_prose_ac
# ---------------------------------------------------------------------------

class TestDemoteProseAc:
    def test_returns_true_with_demotion_reason(self) -> None:
        passed, reason = demote_prose_ac("EVERY sub-agent does something")
        assert passed is True
        assert "prose AC demoted to warning" in reason
        assert "F-R7-531 forward-carry" in reason

    def test_idempotent_across_inputs(self) -> None:
        criterion_a = "EVERY Claude-CLI sub-agent invocation routes through spawn_with_retry"
        criterion_b = "Transient retries do NOT increment refinement_attempts"
        result_a = demote_prose_ac(criterion_a)
        result_b = demote_prose_ac(criterion_b)
        assert result_a == result_b


# ---------------------------------------------------------------------------
# log_prose_ac_demoted
# ---------------------------------------------------------------------------

class TestLogProseAcDemoted:
    def test_emits_json_log_line(self, caplog: pytest.LogCaptureFixture) -> None:
        criterion = "EVERY sub-agent routes through spawn_with_retry"
        feature_id = "b6873bac-test"

        with caplog.at_level(logging.INFO, logger="bob3.verification.prose_demotion"):
            log_prose_ac_demoted(criterion, feature_id=feature_id)

        assert len(caplog.records) >= 1
        record = caplog.records[-1]
        data = json.loads(record.getMessage())
        assert data["event"] == "PROSE_AC_DEMOTED"
        assert data["criterion"] == criterion
        assert data["feature_id"] == feature_id
        assert "timestamp" in data

    def test_feature_id_none_allowed(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="bob3.verification.prose_demotion"):
            log_prose_ac_demoted("some prose criterion")

        assert len(caplog.records) >= 1
        data = json.loads(caplog.records[-1].getMessage())
        assert data["feature_id"] is None

    def test_timestamp_is_iso8601(self, caplog: pytest.LogCaptureFixture) -> None:
        from datetime import datetime
        with caplog.at_level(logging.INFO, logger="bob3.verification.prose_demotion"):
            log_prose_ac_demoted("some prose criterion", feature_id="feat-123")

        data = json.loads(caplog.records[-1].getMessage())
        # Should parse without exception
        dt = datetime.fromisoformat(data["timestamp"])
        assert dt.tzinfo is not None
