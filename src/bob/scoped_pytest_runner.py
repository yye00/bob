"""Scoped pytest runner — verifier MUST scope pytest to the current feature's own tests.

The verifier's ``tests_pass`` step MUST call :func:`run_scoped_pytest` instead
of invoking ``pytest tests/``. Running the full tree causes pytest-xdist
``--maxfail=20`` to trip on accumulated failures from prior features before the
current feature's own tests ever execute (root cause: F-R7-fbd68fee).

Public API
----------
run_scoped_pytest(feature_id, acs, workspace, *, extra_args=None, timeout=300)
    Run pytest scoped to *feature_id*'s own test paths.  Returns a
    :class:`~bob.verifier.pytest_scoping.ScopedPytestResult`.

ScopedPytestResult
    Dataclass holding returncode, stdout, stderr, and the scoped paths used.

ScopedPytestSkipped
    Exception raised when no scoped paths are found (caller should skip).

SiblingTestCollectionError
    Exception raised when a sibling feature subtree would be collected.
"""

from __future__ import annotations

from pathlib import Path

from bob.verifier.pytest_scoping import (
    ScopedPytestResult,  # noqa: F401 — re-exported
    ScopedPytestSkipped,  # noqa: F401 — re-exported
    scoped_pytest_runner as _scoped_pytest_runner,
)
from bob.verification.per_feature_test_scope import (
    SiblingTestCollectionError,  # noqa: F401 — re-exported
)

__all__ = [
    "ScopedPytestResult",
    "ScopedPytestSkipped",
    "SiblingTestCollectionError",
    "run_scoped_pytest",
]


def run_scoped_pytest(
    feature_id: str,
    acs: list[str],
    workspace: str | Path,
    *,
    extra_args: list[str] | None = None,
    timeout: int = 300,
) -> "ScopedPytestResult":
    """Run pytest scoped to *feature_id*'s own test paths.

    This is the canonical entry point the verifier's ``tests_pass`` step must
    call. It delegates to :func:`bob.verifier.pytest_scoping.scoped_pytest_runner`,
    scoping pytest to ONLY paths declared in the feature's ``pytest:`` ACs plus
    the feature's own ``tests/<feature_id>/`` subtree.

    Args:
        feature_id: The feature's UUID string.
        acs:        The feature's acceptance criteria list. ``pytest:`` AC
                    entries supply explicit test paths.
        workspace:  Repository root (directory containing ``tests/``).
        extra_args: Additional pytest flags to append (e.g. ``["-v", "-x"]``).
                    Must not include bare ``tests/`` or sibling subtree paths.
        timeout:    Maximum seconds to allow the subprocess.  Defaults to 300 s.

    Returns:
        :class:`~bob.verifier.pytest_scoping.ScopedPytestResult` with
        returncode, stdout, stderr, and the resolved scoped paths.

    Raises:
        ScopedPytestSkipped: When no test paths are found for *feature_id*.
            The caller should skip the pytest step rather than falling back to
            the full test suite.
        SiblingTestCollectionError: If the resolved paths would pull in a
            sibling feature subtree.
    """
    return _scoped_pytest_runner(
        feature_id,
        acs,
        workspace,
        extra_args=extra_args,
        timeout=timeout,
    )
