"""Explicit finite public development route, without an isolation claim.

This route is selected by the controller's private, hash-bound supervisor config.
It cannot satisfy or disable requests for an external/independent verifier.
"""

from __future__ import annotations

import os
from pathlib import Path

from bob.finite_budget import load_finite_profile


def load_public_execution(*, workspace=None, environ=None):
    env = os.environ if environ is None else environ
    path = env.get("BOB_PUBLIC_EXECUTION_CONFIG")
    digest = env.get("BOB_PUBLIC_EXECUTION_CONFIG_SHA256")
    if path is None and digest is None:
        return None
    if not path or not digest:
        raise ValueError("public execution requires both controller config bindings")

    from bob.finite_supervisor import feature_snapshot, load_config

    config = load_config(path, digest)
    profile = load_finite_profile(env)
    if (
        profile is None
        or profile.path != Path(config["profile"])
        or profile.sha256 != config["profile_sha256"]
    ):
        raise ValueError("public execution requires its exact finite profile")
    profile.assert_outside(config["workspace"])
    if workspace is not None and Path(workspace).resolve() != Path(config["workspace"]):
        raise ValueError("public execution workspace binding mismatch")
    feature_snapshot(config)

    # Budget/model/hermetic settings do not by themselves assert isolation. A
    # genuine boundary request must never be satisfied by this public route.
    for key in (
        "BOB_EXTERNAL_VERIFIER_REQUIRED",
        "BOB_INDEPENDENT_TEST_WRITER",
        "BOB_ADMITTED_PACKET_REQUIRED",
    ):
        if env.get(key, "").strip().lower() not in {
            "",
            "0",
            "false",
            "no",
            "off",
            "disabled",
        }:
            raise ValueError("public execution cannot replace an independent boundary")
    for key in (
        "BOB_CANDIDATE_EXEC_WRAPPER",
        "BOB_CANDIDATE_TEST_PYTHON",
        "BOB_PACKET_PROJECTION",
        "BOB_PACKET_PROJECTION_SHA256",
        "BOB_PACKET_EXECUTION_PROFILE",
        "BOB_PACKET_EXECUTION_PROFILE_SHA256",
    ):
        if env.get(key, "").strip():
            raise ValueError("public execution cannot replace an independent boundary")
    for key in ("BOB_EVALUATOR_REQUIRED", "BOB_CLAUDE_HERMETIC"):
        if env.get(key, "").strip().lower() not in {"1", "true", "yes", "on"}:
            raise ValueError(f"public execution requires {key}")
    if env.get("BOB_REQUIRED_MODEL") != profile.model_id:
        raise ValueError("public execution requires its exact selected model")
    return config


def public_test_command(config):
    verification = config["verification"]
    return [
        verification["python"],
        "-I",
        "-B",
        "-m",
        "pytest",
        verification["test_dir"],
        "-q",
        "--color=no",
        "--maxfail=0",
        "-p",
        "no:cacheprovider",
    ]
