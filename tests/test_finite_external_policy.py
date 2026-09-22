"""Offline policy checks only; fixture wrappers are never deployed or executed."""

import os
import sys
from pathlib import Path

import pytest

from bob.candidate_exec import candidate_argv, validate_candidate_execution_policy
from bob.finite_budget import DIGEST_ENV, PROFILE_ENV, load_finite_profile
from tests.test_finite_supervisor import campaign  # noqa: F401


@pytest.fixture
def external(campaign, monkeypatch):  # noqa: F811 - shared pytest fixture
    for key in list(os.environ):
        if key.startswith("BOB_"):
            monkeypatch.delenv(key)
    controller = Path(campaign["controller"])
    wrapper = controller / "synthetic-wrapper-not-an-isolation-service"
    wrapper.write_text("#!/bin/sh\nexit 77\n")
    wrapper.chmod(0o700)
    sessions = controller / "sessions"
    sessions.mkdir()
    values = {
        PROFILE_ENV: campaign["profile"],
        DIGEST_ENV: campaign["profile_sha256"],
        "BOB_EXTERNAL_VERIFIER_REQUIRED": "1",
        "BOB_INDEPENDENT_TEST_WRITER": "required",
        "BOB_EVALUATOR_REQUIRED": "1",
        "BOB_CLAUDE_HERMETIC": "1",
        "BOB_DYNAMIC_DECOMPOSITION": "disabled",
        "BOB_CANDIDATE_EXEC_WRAPPER": str(wrapper),
        "BOB_CANDIDATE_TEST_PYTHON": sys.executable,
        "BOB_DATABASE_PATH": campaign["database"],
        "BOB_SESSIONS_ROOT": str(sessions),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("BOB_REQUIRED_MODEL", load_finite_profile().model_id)
    return campaign


def test_finite_external_route_accepts_exact_model_and_keeps_wrapper(external):
    validate_candidate_execution_policy(workspace=external["workspace"])
    argv = candidate_argv([sys.executable, "-m", "pytest", "-q"])
    assert argv[:5] == [
        os.environ["BOB_CANDIDATE_EXEC_WRAPPER"],
        sys.executable,
        "-I",
        "-B",
        "-c",
    ]
    assert "BOB_PUBLIC_EXECUTION_CONFIG" not in os.environ


@pytest.mark.parametrize(
    "name",
    [
        "BOB_EXTERNAL_VERIFIER_REQUIRED",
        "BOB_INDEPENDENT_TEST_WRITER",
        "BOB_EVALUATOR_REQUIRED",
        "BOB_CLAUDE_HERMETIC",
        "BOB_DYNAMIC_DECOMPOSITION",
        "BOB_CANDIDATE_EXEC_WRAPPER",
        "BOB_CANDIDATE_TEST_PYTHON",
        "BOB_DATABASE_PATH",
        "BOB_SESSIONS_ROOT",
    ],
)
def test_finite_profile_does_not_waive_any_external_boundary(
    external, monkeypatch, name
):
    monkeypatch.delenv(name)
    with pytest.raises((RuntimeError, ValueError)):
        validate_candidate_execution_policy(workspace=external["workspace"])


@pytest.mark.parametrize(
    "model", ["claude-opus-4-8", "haiku", "", "claude-haiku-4-5-20251001 "]
)
def test_external_finite_route_rejects_legacy_alias_or_model_drift(
    external, monkeypatch, model
):
    monkeypatch.setenv("BOB_REQUIRED_MODEL", model)
    with pytest.raises(RuntimeError, match="exact profile model"):
        validate_candidate_execution_policy(workspace=external["workspace"])


def test_invalid_finite_profile_does_not_fall_back_to_legacy_opus(
    external, monkeypatch
):
    monkeypatch.setenv("BOB_REQUIRED_MODEL", "claude-opus-4-8")
    monkeypatch.setenv(DIGEST_ENV, "0" * 64)
    with pytest.raises(ValueError):
        validate_candidate_execution_policy(workspace=external["workspace"])


def test_candidate_owned_finite_profile_rejects(external, monkeypatch):
    private = Path(external["workspace"]) / "candidate-owned-controller"
    private.mkdir(mode=0o700)
    profile = private / "profile.json"
    profile.write_bytes(Path(external["profile"]).read_bytes())
    profile.chmod(0o400)
    monkeypatch.setenv(PROFILE_ENV, str(profile))
    with pytest.raises(ValueError, match="outside"):
        validate_candidate_execution_policy(workspace=external["workspace"])


def test_no_finite_profile_preserves_legacy_opus_requirement(external, monkeypatch):
    monkeypatch.delenv(PROFILE_ENV)
    monkeypatch.delenv(DIGEST_ENV)
    with pytest.raises(RuntimeError, match="claude-opus-4-8"):
        validate_candidate_execution_policy(workspace=external["workspace"])
    monkeypatch.setenv("BOB_REQUIRED_MODEL", "claude-opus-4-8")
    validate_candidate_execution_policy(workspace=external["workspace"])
