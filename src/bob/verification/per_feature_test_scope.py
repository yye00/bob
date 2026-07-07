"""Per-feature pytest scoping for the verifier's tests_pass step.

Problem: when a workspace has N features and some prior features have broken
test stubs, running ``pytest tests/`` collects ALL feature subtrees. The
pytest-xdist ``--maxfail=20`` trips on the accumulated failures from prior
features before the current feature's own tests ever execute.

Fix: scope every per-feature ``tests_pass`` invocation to ONLY the paths
declared in the feature's own ``pytest:`` ACs plus the feature's own
``tests/<feature_id>/`` subtree. Whole-suite regression detection continues
via the separate F-R7-532 regression-sweep (unchanged).

Public API
----------
scope_pytest_to_feature(feature_id, acs, workspace) -> list[str]
    Return the sorted list of test paths scoped to the current feature.
    Combines pytest: AC paths and the feature's own tests/<feature_id>/
    subtree. Returns an empty list when no paths are found. Never includes
    bare tests/ or sibling feature subtrees.

collect_feature_test_paths(feature_id, acs, workspace) -> set[str]
    Return the set of test paths for this feature (pytest-prefix ACs +
    feature subtree). Returns empty set when neither source exists.

build_scoped_pytest_argv(feature_id, acs, workspace) -> list[str]
    Construct a pytest argv list restricted to the feature's own test paths.
    Never includes the whole tests/ tree.

assert_no_sibling_collection(feature_id, argv, workspace) -> None
    Raise SiblingTestCollectionError if argv would pull in tests from any
    other feature subtree (tests/<uuid>/ where uuid != feature_id).
"""

from __future__ import annotations

import re
from pathlib import Path

# UUID-like pattern: 8-4-4-4-12 hex digits
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class SiblingTestCollectionError(RuntimeError):
    """Raised when a pytest argv would collect tests from a sibling feature subtree."""


def _looks_like_feature_id(name: str) -> bool:
    """Return True if *name* matches the UUID-like feature-id pattern."""
    return bool(_UUID_RE.match(name))


def _validate_inputs(
    feature_id: str,
    acs: list[str],
    workspace: str | Path,
) -> None:
    """Validate the common (feature_id, acs, workspace) inputs.

    Raises:
        ValueError: If *feature_id* is not a non-empty string, *acs* is not a
            list/tuple of strings, or *workspace* is None/empty. This ensures
            the scoping functions fail loudly on malformed input rather than
            silently succeeding (or raising an opaque ``TypeError`` deep in a
            path operation).
    """
    if not isinstance(feature_id, str) or not feature_id.strip():
        raise ValueError(
            f"feature_id must be a non-empty string, got {feature_id!r}"
        )
    if not isinstance(acs, (list, tuple)):
        raise ValueError(
            f"acs must be a list or tuple of strings, got {type(acs).__name__}"
        )
    for ac in acs:
        if not isinstance(ac, str):
            raise ValueError(
                f"every acceptance criterion must be a string, got {ac!r}"
            )
    if workspace is None or (isinstance(workspace, str) and not workspace.strip()):
        raise ValueError(
            f"workspace must be a non-empty path, got {workspace!r}"
        )
    if not isinstance(workspace, (str, Path)):
        raise ValueError(
            f"workspace must be a str or Path, got {type(workspace).__name__}"
        )


def collect_feature_test_paths(
    feature_id: str,
    acs: list[str],
    workspace: str | Path,
) -> set[str]:
    """Return the set of test paths that belong to *feature_id*.

    Sources:
    1. Every ``pytest:`` AC entry (the path portion before any ``::`` node-id).
    2. ``tests/<feature_id>/`` if that directory exists under *workspace*.

    Returns an empty set when neither source yields any paths.

    Args:
        feature_id: The feature's UUID string.
        acs:        The feature's acceptance criteria list.
        workspace:  Repository root (directory containing ``tests/``).

    Raises:
        ValueError: If *feature_id*, *acs*, or *workspace* is malformed.
    """
    _validate_inputs(feature_id, acs, workspace)
    ws = Path(workspace)
    paths: set[str] = set()

    for ac in acs:
        stripped = ac.strip()
        if stripped.lower().startswith("pytest:"):
            expr = stripped[len("pytest:"):].strip()
            # Strip node-id suffix (::ClassName::test_method)
            test_path = expr.split("::")[0].strip()
            if test_path:
                paths.add(test_path)

    # Add the feature's own subtree if it exists.
    feature_dir = ws / "tests" / feature_id
    if feature_dir.is_dir():
        paths.add(f"tests/{feature_id}")

    return paths


def build_scoped_pytest_argv(
    feature_id: str,
    acs: list[str],
    workspace: str | Path,
) -> list[str]:
    """Build a pytest argv restricted to *feature_id*'s own test paths.

    The returned list:
    - Includes ONLY paths from :func:`collect_feature_test_paths`.
    - Adds ``--rootdir=tests/<feature_id>`` when the feature subtree exists.
    - NEVER includes the bare ``tests/`` tree.
    - Raises ``SiblingTestCollectionError`` (via
      :func:`assert_no_sibling_collection`) when the resolved paths would pull
      in another feature's subtree.

    Args:
        feature_id: The feature's UUID string.
        acs:        The feature's acceptance criteria list.
        workspace:  Repository root.

    Returns:
        A pytest argv (list of strings, without the ``python -m pytest`` prefix).
    """
    ws = Path(workspace)
    paths = collect_feature_test_paths(feature_id, acs, ws)

    argv: list[str] = []

    # Add --rootdir when the feature subtree exists.
    feature_dir = ws / "tests" / feature_id
    if feature_dir.is_dir():
        argv += [f"--rootdir=tests/{feature_id}"]

    argv += sorted(paths)

    assert_no_sibling_collection(feature_id, argv, ws)
    return argv


def assert_no_sibling_collection(
    feature_id: str,
    argv: list[str],
    workspace: str | Path,
) -> None:
    """Raise SiblingTestCollectionError if *argv* would collect sibling tests.

    A "sibling feature subtree" is any path component that matches the UUID
    pattern AND is not *feature_id*. This detects both:
    - Explicit paths like ``tests/<other_uuid>/test_foo.py``.
    - Bare ``tests/`` (which would collect everything).

    Args:
        feature_id: The current feature's UUID.
        argv:       The pytest argv to inspect.
        workspace:  Unused here; reserved for future absolute-path resolution.

    Raises:
        SiblingTestCollectionError: If any path in *argv* would pull in a
            sibling feature subtree.
    """
    for token in argv:
        # Skip option flags.
        if token.startswith("-"):
            continue

        # Strip leading "./" for normalisation.
        token_norm = token.lstrip("./")

        # Bare "tests/" or "tests" without a feature subtree → pulls everything.
        parts = Path(token_norm).parts
        if parts and parts[0] == "tests":
            if len(parts) == 1:
                # Bare tests/ — would collect all features.
                raise SiblingTestCollectionError(
                    f"pytest argv contains bare 'tests/' which would collect all feature subtrees; "
                    f"scope it to tests/{feature_id}/ instead. argv={argv!r}"
                )
            if len(parts) >= 2 and _looks_like_feature_id(parts[1]) and parts[1] != feature_id:
                raise SiblingTestCollectionError(
                    f"pytest argv references sibling feature subtree tests/{parts[1]}/ "
                    f"(current feature_id={feature_id}). argv={argv!r}"
                )


def scope_pytest_to_feature(
    feature_id: str,
    acs: list[str],
    workspace: str | Path,
) -> list[str]:
    """Return the sorted list of test paths scoped to *feature_id*'s own tests.

    This is the primary entry point for the verifier's ``tests_pass`` step.
    It ensures pytest is NEVER run against the whole ``tests/`` tree or any
    sibling feature subtree — only the paths that belong to *feature_id*:

    1. Every ``pytest:`` AC entry (path portion, stripped of ``::`` node-ids).
    2. ``tests/<feature_id>/`` when that directory exists under *workspace*.

    The returned paths are safe to pass directly to ``python -m pytest``; they
    will never trigger collection of other features' broken test stubs.

    Args:
        feature_id: The feature's UUID string.
        acs:        The feature's acceptance criteria list.
        workspace:  Repository root (directory containing ``tests/``).

    Returns:
        A sorted list of test paths for this feature. Returns an empty list
        when neither the ``pytest:`` ACs nor the feature's subtree yield any
        paths. The caller should treat an empty list as "no tests to run"
        and skip the pytest step rather than falling back to the full suite.

    Raises:
        SiblingTestCollectionError: If the resolved paths would pull in tests
            from another feature's subtree (defensive guard).
    """
    paths = collect_feature_test_paths(feature_id, acs, workspace)

    scoped = sorted(paths)

    # Validate — this should never raise for well-formed inputs, but acts
    # as a defensive guard against accidental sibling inclusion.
    assert_no_sibling_collection(feature_id, scoped, workspace)

    return scoped
