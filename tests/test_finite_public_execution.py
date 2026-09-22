"""Real local policy and pytest dispatch; no provider or isolation simulation."""

import os
from pathlib import Path

import pytest

from bob.candidate_exec import candidate_argv, validate_candidate_execution_policy
from bob.finite_budget import load_finite_profile
from bob.finite_supervisor import child_environment
from bob.public_execution import load_public_execution, public_test_command
from tests.test_finite_supervisor import campaign  # noqa: F401


@pytest.fixture
def public(campaign, monkeypatch):  # noqa: F811 - imported shared pytest fixture
    env = child_environment(campaign)
    env["BOB_REQUIRED_MODEL"] = load_finite_profile(env).model_id
    for key in list(os.environ):
        if key.startswith("BOB_"):
            monkeypatch.delenv(key)
    for key, value in env.items():
        if key.startswith(("BOB_", "PYTEST_")):
            monkeypatch.setenv(key, value)
    return campaign


def test_explicit_public_route_accepts_finite_model_without_claiming_isolation(public):
    validate_candidate_execution_policy(workspace=public["workspace"])
    assert load_public_execution()["schema_version"].endswith(".v2")
    assert "BOB_EXTERNAL_VERIFIER_REQUIRED" not in os.environ


@pytest.mark.parametrize(
    "missing",
    [
        "BOB_PUBLIC_EXECUTION_CONFIG",
        "BOB_PUBLIC_EXECUTION_CONFIG_SHA256",
        "BOB_FINITE_EXECUTION_PROFILE",
        "BOB_EVALUATOR_REQUIRED",
        "BOB_CLAUDE_HERMETIC",
        "BOB_REQUIRED_MODEL",
    ],
)
def test_incomplete_public_route_fails_closed(public, monkeypatch, missing):
    monkeypatch.delenv(missing)
    with pytest.raises((ValueError, RuntimeError)):
        validate_candidate_execution_policy(workspace=public["workspace"])


@pytest.mark.parametrize(
    "boundary",
    [
        "BOB_EXTERNAL_VERIFIER_REQUIRED",
        "BOB_INDEPENDENT_TEST_WRITER",
        "BOB_ADMITTED_PACKET_REQUIRED",
        "BOB_CANDIDATE_EXEC_WRAPPER",
        "BOB_CANDIDATE_TEST_PYTHON",
        "BOB_PACKET_PROJECTION",
        "BOB_PACKET_EXECUTION_PROFILE",
    ],
)
def test_public_config_cannot_disable_a_requested_boundary(
    public, monkeypatch, boundary
):
    monkeypatch.setenv(boundary, "1")
    with pytest.raises(ValueError, match="independent boundary"):
        validate_candidate_execution_policy(workspace=public["workspace"])


@pytest.mark.parametrize("mutation", ["model", "workspace", "hash"])
def test_public_identity_mismatch_rejects(public, monkeypatch, tmp_path, mutation):
    workspace = public["workspace"]
    if mutation == "model":
        monkeypatch.setenv("BOB_REQUIRED_MODEL", "different-model")
    elif mutation == "workspace":
        workspace = str(tmp_path)
    else:
        monkeypatch.setenv("BOB_PUBLIC_EXECUTION_CONFIG_SHA256", "0" * 64)
    with pytest.raises(ValueError):
        validate_candidate_execution_policy(workspace=workspace)


def test_absent_explicit_public_config_keeps_legacy_partial_policy_rejection(
    public, monkeypatch
):
    monkeypatch.delenv("BOB_PUBLIC_EXECUTION_CONFIG")
    monkeypatch.delenv("BOB_PUBLIC_EXECUTION_CONFIG_SHA256")
    with pytest.raises(RuntimeError, match="partial hardened"):
        validate_candidate_execution_policy(workspace=public["workspace"])


def test_public_command_uses_selected_python_without_hardcoded_mount(public):
    command = candidate_argv(["python", "-m", "pytest", "app/tests/public"])
    assert command[:3] == [public["verification"]["python"], "-I", "-B"]
    assert "/workspace/app/src" not in " ".join(command)


def write_public_project(public):
    workspace = Path(public["workspace"])
    (workspace / "pytest.ini").write_text("[pytest]\npythonpath = app/src\n")
    (workspace / "app/src/example.py").write_text("def total():\n    return 10\n")
    (workspace / "app/tests/public/test_example.py").write_text(
        "from example import total\ndef test_total():\n    assert total() == 10\n"
    )
    return workspace


def test_native_snapshot_collects_app_tests_and_detects_real_regression(public):
    from bob.orchestrator.run_loop import capture_pytest_snapshot

    workspace = write_public_project(public)
    before = capture_pytest_snapshot(str(workspace))
    assert before and len(before) == 1 and all(before.values())
    (workspace / "app/src/example.py").write_text("def total():\n    return 99\n")
    after = capture_pytest_snapshot(str(workspace))
    assert after and set(after) == set(before) and not any(after.values())


def test_native_checklist_uses_full_selected_suite_and_does_not_skip_python(public):
    from bob.superpowers import run_verification_checklist

    workspace = write_public_project(public)
    result = run_verification_checklist(
        workspace=str(workspace), enable_security_check=False
    )
    check = next(c for c in result["checks"] if c["name"] == "tests_pass")
    assert check["passed"] is True and check.get("severity") != "warning", check
    (workspace / "app/tests/public/test_regression.py").write_text(
        "def test_other():\n    assert False\n"
    )
    result = run_verification_checklist(
        workspace=str(workspace), enable_security_check=False
    )
    check = next(c for c in result["checks"] if c["name"] == "tests_pass")
    assert check["passed"] is False, check


def test_override_of_selected_test_command_rejects(public):
    from bob.superpowers import run_verification_checklist

    with pytest.raises(ValueError, match="conflicts"):
        run_verification_checklist(
            workspace=public["workspace"], exact_test_command=["true"]
        )
    assert public_test_command(public)[-4:] == [
        "--color=no",
        "--maxfail=0",
        "-p",
        "no:cacheprovider",
    ]


@pytest.mark.parametrize(
    "extra_test",
    [
        "import pytest\n@pytest.mark.skip(reason='synthetic exclusion')\ndef test_skipped():\n    pass\n",
        "import nonexistent_public_fixture_dependency\n",
    ],
)
def test_public_suite_cannot_promote_skips_or_collection_errors(public, extra_test):
    from bob.superpowers import run_verification_checklist

    workspace = write_public_project(public)
    (workspace / "app/tests/public/test_extra.py").write_text(extra_test)
    result = run_verification_checklist(
        workspace=str(workspace), enable_security_check=False
    )
    check = next(c for c in result["checks"] if c["name"] == "tests_pass")
    assert check["passed"] is False and check["severity"] == "error", check
