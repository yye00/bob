"""Scoped pytest runner for the verifier's tests_pass step.

The verifier MUST NOT run the full ``tests/`` tree during per-feature
verification. Running the entire suite causes pytest-xdist's ``--maxfail``
to trip on accumulated failures from prior features before the current
feature's own tests ever execute, burning retry budget and producing false
negatives (see F-R7-fbd68fee root-cause analysis).

This module provides :func:`scoped_pytest_runner` — the single entry point
the verifier's ``tests_pass`` step must call. It:

1. Resolves the scoped test paths via :func:`scope_pytest_to_feature`.
2. Builds a subprocess-ready argv list restricted to those paths.
3. Invokes ``python -m pytest`` as a subprocess and returns the result.
4. NEVER collects tests from sibling feature subtrees.

Public API
----------
scoped_pytest_runner(feature_id, acs, workspace, *, extra_args=None) -> ScopedPytestResult
    Run pytest scoped to *feature_id*'s own test paths.

ScopedPytestResult
    Dataclass holding returncode, stdout, stderr, and the scoped paths used.

ScopedPytestSkipped
    Exception raised when no scoped paths are found (caller should skip).
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from bob3.verification.per_feature_test_scope import (
    SiblingTestCollectionError,  # noqa: F401 — re-exported for convenience
    collect_feature_test_paths,
    scope_pytest_to_feature,
)


class ScopedPytestSkipped(RuntimeError):
    """Raised when no test paths are found for the feature.

    The caller should treat this as "no tests to run" and skip the
    pytest step rather than falling back to the full suite.
    """


@dataclass
class ScopedPytestResult:
    """Result of a scoped pytest run via :func:`scoped_pytest_runner`."""

    returncode: int
    stdout: str
    stderr: str
    scoped_paths: list[str] = field(default_factory=list)
    feature_id: str = ""
    workspace: str = ""

    @property
    def passed(self) -> bool:
        """True when pytest exited with code 0 (all collected tests passed)."""
        return self.returncode == 0

    @property
    def no_tests_collected(self) -> bool:
        """True when pytest exited with code 5 (no tests were collected)."""
        return self.returncode == 5


def scoped_pytest_runner(
    feature_id: str,
    acs: list[str],
    workspace: str | Path,
    *,
    extra_args: list[str] | None = None,
    timeout: int = 300,
) -> ScopedPytestResult:
    """Run pytest scoped to *feature_id*'s own test paths.

    This is the single entry point the verifier's ``tests_pass`` step must
    call. It resolves the scoped paths via :func:`scope_pytest_to_feature`,
    builds a subprocess argv, and runs ``python -m pytest`` restricted to
    those paths. It NEVER runs the full ``tests/`` tree or any sibling
    feature subtree.

    Args:
        feature_id: The feature's UUID string.
        acs:        The feature's acceptance criteria list. ``pytest:`` AC
                    entries supply explicit test paths; the feature's own
                    ``tests/<feature_id>/`` subtree is always included when
                    present.
        workspace:  Repository root (directory containing ``tests/``).
        extra_args: Additional pytest flags to append (e.g. ``["-v", "-x"]``).
                    Must not include bare ``tests/`` or sibling subtree paths.
        timeout:    Maximum seconds to allow the pytest subprocess to run.
                    Defaults to 300 s.

    Returns:
        :class:`ScopedPytestResult` with returncode, stdout, stderr, and the
        resolved scoped paths.

    Raises:
        ScopedPytestSkipped: When no test paths are found for *feature_id*.
            The caller should treat this as "no tests to run" and skip the
            pytest step rather than falling back to the full test suite.
        SiblingTestCollectionError: If the resolved paths or *extra_args*
            would pull in a sibling feature subtree (defensive guard).
    """
    ws = Path(workspace)
    scoped_paths = scope_pytest_to_feature(feature_id, acs, ws)

    if not scoped_paths:
        raise ScopedPytestSkipped(
            f"No test paths found for feature {feature_id}. "
            f"Ensure the feature has 'pytest:' ACs or a tests/{feature_id}/ subtree. "
            f"The caller should skip the pytest step rather than falling back to "
            f"the full tests/ suite."
        )

    cmd = [sys.executable, "-m", "pytest"] + scoped_paths
    if extra_args:
        cmd.extend(extra_args)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(ws),
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return ScopedPytestResult(
            returncode=-1,
            stdout=stdout,
            stderr=f"pytest timed out after {timeout}s\n{stderr}",
            scoped_paths=scoped_paths,
            feature_id=feature_id,
            workspace=str(ws),
        )

    return ScopedPytestResult(
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        scoped_paths=scoped_paths,
        feature_id=feature_id,
        workspace=str(ws),
    )


def build_scoped_argv(
    feature_id: str,
    acs: list[str],
    workspace: str | Path,
    *,
    extra_args: list[str] | None = None,
) -> list[str]:
    """Build a pytest argv restricted to *feature_id*'s own test paths.

    A thin helper over :func:`scope_pytest_to_feature` that returns the
    argv list (without ``python -m pytest``) for callers that want to
    construct the subprocess command themselves.

    Args:
        feature_id: The feature's UUID string.
        acs:        The feature's acceptance criteria list.
        workspace:  Repository root.
        extra_args: Additional pytest flags to append.

    Returns:
        List of strings forming the pytest argv (no paths → empty list of
        test paths, extra_args still appended).

    Raises:
        SiblingTestCollectionError: If any resolved path would pull in a
            sibling feature subtree.
    """
    ws = Path(workspace)
    scoped_paths = scope_pytest_to_feature(feature_id, acs, ws)
    argv = list(scoped_paths)
    if extra_args:
        argv.extend(extra_args)
    return argv
