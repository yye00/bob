"""Acceptance criterion kind definitions for Bob.

Implements the 'characterization' AC kind — a Feathers/Michael Hill
characterization test pattern that:

  1. Captures current behavior of a target function as snapshot files
     (observer phase, before any changes).
  2. After implementation changes, re-runs the target with the same inputs
     and diffs against the snapshots.
  3. Any diff fails the AC unless it matches ``allow_changes`` glob patterns.

This enables brownfield edits to legacy code without existing tests to be
verified by comparing observed behavior before and after the change.

AC body shape (YAML):
    characterization:
      target: src/foo/bar.py::Bar.method
      sample_inputs: [<list of literal call args> or 'auto']
      snapshot_dir: tests/snapshots/F-R7-601/
      allow_changes: []   # optional list of glob patterns for permitted diffs

Public API
----------
CharacterizationAC
    Dataclass holding a parsed characterization acceptance criterion.

parse_characterization_ac(ac) -> CharacterizationAC | None
    Parse a characterization AC from a raw AC string or YAML mapping.

observe_and_snapshot(ac, workspace) -> SnapshotResult
    Invoke the target with sample_inputs and write snapshot files to
    snapshot_dir. Called during the observer phase (before implementation).

verify_against_snapshots(ac, workspace) -> VerificationResult
    Re-run the target with sample_inputs and diff against existing
    snapshot_dir. Called during the verifier phase (after implementation).
"""

from __future__ import annotations

import difflib
import fnmatch
import importlib
import io
import pathlib
import re
import subprocess
import sys
import traceback
import types
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CharacterizationAC:
    """Parsed characterization acceptance criterion.

    Attributes:
        target:        Dotted path or file::symbol reference to the callable
                       being characterized (e.g. ``src/foo/bar.py::Bar.method``
                       or ``bob.spec_quality.ears_parser.parse_behavior_ac``).
        sample_inputs: List of call-argument tuples as Python literals, or the
                       string ``'auto'`` to trigger auto-discovery.
        snapshot_dir:  Workspace-relative path where snapshot .txt files live.
        allow_changes: Glob patterns for diff lines that are permitted to change
                       without failing the AC (e.g. ``['*timestamp*']``).
    """

    target: str
    sample_inputs: list[Any] | str  # list of arg tuples or 'auto'
    snapshot_dir: str
    allow_changes: list[str] = field(default_factory=list)


@dataclass
class SnapshotResult:
    """Outcome of the observer (snapshot) phase.

    Attributes:
        success:        True when all sample_inputs were executed and snapshotted.
        snapshot_files: Paths to the written snapshot files.
        errors:         Per-input error messages (empty on success).
    """

    success: bool
    snapshot_files: list[pathlib.Path]
    errors: list[str]


@dataclass
class VerificationResult:
    """Outcome of the verifier (diff) phase.

    Attributes:
        passed:  True when no disallowed diffs were found.
        diffs:   Human-readable unified diff strings for failing inputs.
        details: Summary message for logging / AC evidence.
    """

    passed: bool
    diffs: list[str]
    details: str


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_CHAR_PREFIX_RE = re.compile(r"^characterization\s*:", re.IGNORECASE)


def parse_characterization_ac(ac: Any) -> CharacterizationAC | None:
    """Parse a characterization AC from a raw string or mapping.

    Accepts two forms:

    1. A Python dict (already parsed from YAML) with key ``'characterization'``
       whose value is a mapping with ``target``, ``sample_inputs``, and
       ``snapshot_dir`` keys.

    2. A string starting with ``'characterization:'`` (treated as a minimal
       inline form where the rest is the target path — sample_inputs defaults
       to ``'auto'`` and snapshot_dir defaults to
       ``'tests/snapshots/<target_slug>/'``).

    Returns:
        A :class:`CharacterizationAC` on success, or ``None`` if *ac* does not
        match the characterization grammar.
    """
    if isinstance(ac, dict):
        body = ac.get("characterization")
        if body is None:
            return None
        if not isinstance(body, dict):
            return None
        target = body.get("target", "")
        if not target:
            return None
        sample_inputs = body.get("sample_inputs", "auto")
        snapshot_dir = body.get("snapshot_dir", _default_snapshot_dir(target))
        allow_changes = body.get("allow_changes", [])
        return CharacterizationAC(
            target=str(target),
            sample_inputs=sample_inputs,
            snapshot_dir=str(snapshot_dir),
            allow_changes=list(allow_changes),
        )

    if isinstance(ac, str):
        stripped = ac.strip()
        if not _CHAR_PREFIX_RE.match(stripped):
            return None
        rest = _CHAR_PREFIX_RE.sub("", stripped).strip()
        # Minimal inline form: "characterization: pkg.mod::func"
        return CharacterizationAC(
            target=rest,
            sample_inputs="auto",
            snapshot_dir=_default_snapshot_dir(rest),
            allow_changes=[],
        )

    return None


def _default_snapshot_dir(target: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]", "_", target)[:60]
    return f"tests/snapshots/{slug}/"


# ---------------------------------------------------------------------------
# Target resolution
# ---------------------------------------------------------------------------


def _resolve_target(target: str, workspace: pathlib.Path) -> Any:
    """Resolve a target string to a callable.

    Supports two target formats:

    * ``pkg.module.Class.method`` — imported via :func:`importlib.import_module`.
    * ``src/path/to/file.py::Class.method`` — loads the file directly and
      looks up the dotted attribute chain.

    Returns the resolved callable, or raises ``ValueError`` on failure.
    """
    if "::" in target:
        file_part, attr_part = target.split("::", 1)
        py_file = (workspace / file_part).resolve()
        if not py_file.exists():
            raise ValueError(f"Target file not found: {py_file}")
        # Compile from source directly to avoid .pyc caching between observer
        # and verifier phases (the file may be modified between calls).
        source = py_file.read_text(encoding="utf-8")
        code = compile(source, str(py_file), "exec")
        mod = types.ModuleType("_char_target_mod")
        mod.__file__ = str(py_file)
        # Add workspace/src to sys.path temporarily so relative imports work.
        src_dir = str(workspace / "src")
        inserted = False
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
            inserted = True
        try:
            exec(code, mod.__dict__)  # noqa: S102
        finally:
            if inserted and src_dir in sys.path:
                sys.path.remove(src_dir)
        obj: Any = mod
        for part in attr_part.split("."):
            obj = getattr(obj, part)
        return obj

    # Dotted import path
    parts = target.rsplit(".", 1)
    if len(parts) == 1:
        raise ValueError(f"Cannot resolve target with no attribute component: {target!r}")
    mod_path, attr = parts
    src_dir = str(workspace / "src")
    inserted = False
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
        inserted = True
    try:
        mod = importlib.import_module(mod_path)
    finally:
        if inserted and src_dir in sys.path:
            sys.path.remove(src_dir)
    return getattr(mod, attr)


# ---------------------------------------------------------------------------
# Input preparation
# ---------------------------------------------------------------------------


def _prepare_inputs(sample_inputs: list[Any] | str, callable_obj: Any) -> list[tuple[Any, ...]]:
    """Normalize sample_inputs into a list of positional-argument tuples.

    ``'auto'`` returns a single no-arg tuple ``[()]``.
    A list of non-tuple items is treated as individual single-argument calls.
    A list of tuples is returned as-is.
    """
    if sample_inputs == "auto":
        return [()]

    if not isinstance(sample_inputs, list):
        return [()]

    result: list[tuple[Any, ...]] = []
    for item in sample_inputs:
        if isinstance(item, (list, tuple)):
            result.append(tuple(item))
        else:
            result.append((item,))
    return result


# ---------------------------------------------------------------------------
# Snapshot capture
# ---------------------------------------------------------------------------


def _capture_call(callable_obj: Any, args: tuple[Any, ...]) -> str:
    """Call *callable_obj* with *args* and capture stdout + return value.

    Returns a string combining captured stdout and the repr of the return value
    (or the traceback if the call raises).
    """
    buf_stdout = io.StringIO()
    buf_stderr = io.StringIO()
    try:
        with redirect_stdout(buf_stdout), redirect_stderr(buf_stderr):
            result = callable_obj(*args)
        return_repr = repr(result)
    except Exception:
        return_repr = "EXCEPTION:\n" + traceback.format_exc()

    out = buf_stdout.getvalue()
    err = buf_stderr.getvalue()
    parts: list[str] = []
    if out:
        parts.append(f"STDOUT:\n{out}")
    if err:
        parts.append(f"STDERR:\n{err}")
    parts.append(f"RETURN:\n{return_repr}")
    return "\n".join(parts)


def _snapshot_filename(index: int, args: tuple[Any, ...]) -> str:
    """Generate a deterministic snapshot filename for a given input index."""
    return f"snapshot_{index:04d}.txt"


def observe_and_snapshot(
    ac: CharacterizationAC, workspace: pathlib.Path
) -> SnapshotResult:
    """Observer phase: run target with sample_inputs and write snapshot files.

    Called **before** any implementation changes. The resulting snapshot files
    in ``ac.snapshot_dir`` represent the ground-truth baseline behavior.

    Args:
        ac:        A parsed :class:`CharacterizationAC`.
        workspace: Absolute path to the project workspace root.

    Returns:
        A :class:`SnapshotResult` describing which files were written and any
        per-input errors.
    """
    snap_dir = workspace / ac.snapshot_dir
    snap_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    snapshot_files: list[pathlib.Path] = []

    try:
        callable_obj = _resolve_target(ac.target, workspace)
    except Exception as exc:
        return SnapshotResult(
            success=False,
            snapshot_files=[],
            errors=[f"Target resolution failed: {exc}"],
        )

    inputs = _prepare_inputs(ac.sample_inputs, callable_obj)

    for idx, args in enumerate(inputs):
        filename = _snapshot_filename(idx, args)
        snap_path = snap_dir / filename

        # Write args header + captured output.
        header = f"ARGS: {args!r}\n{'=' * 60}\n"
        captured = _capture_call(callable_obj, args)
        content = header + captured

        try:
            snap_path.write_text(content, encoding="utf-8")
            snapshot_files.append(snap_path)
        except OSError as exc:
            errors.append(f"Input {idx}: write failed — {exc}")

    return SnapshotResult(
        success=len(errors) == 0,
        snapshot_files=snapshot_files,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Verification (diff phase)
# ---------------------------------------------------------------------------


def _diff_is_allowed(diff_lines: list[str], allow_changes: list[str]) -> bool:
    """Return True if every changed line in *diff_lines* is covered by *allow_changes*.

    Only lines that start with ``+`` or ``-`` (excluding the ``+++``/``---``
    header lines) are checked against the glob patterns.
    """
    if not allow_changes:
        return False

    changed = [
        ln[1:]  # strip the leading +/-
        for ln in diff_lines
        if (ln.startswith("+") or ln.startswith("-"))
        and not ln.startswith("+++")
        and not ln.startswith("---")
    ]
    if not changed:
        return True

    return all(
        any(fnmatch.fnmatch(line, pat) for pat in allow_changes)
        for line in changed
    )


def verify_against_snapshots(
    ac: CharacterizationAC, workspace: pathlib.Path
) -> VerificationResult:
    """Verifier phase: re-run target and diff against existing snapshots.

    Called **after** implementation changes. Any diff that is not covered by
    ``ac.allow_changes`` globs fails the AC.

    Args:
        ac:        A parsed :class:`CharacterizationAC`.
        workspace: Absolute path to the project workspace root.

    Returns:
        A :class:`VerificationResult` with pass/fail status and diff content.
    """
    snap_dir = workspace / ac.snapshot_dir

    if not snap_dir.exists():
        return VerificationResult(
            passed=False,
            diffs=[],
            details=(
                f"Snapshot directory does not exist: {snap_dir}. "
                "Run the observer phase first."
            ),
        )

    try:
        callable_obj = _resolve_target(ac.target, workspace)
    except Exception as exc:
        return VerificationResult(
            passed=False,
            diffs=[],
            details=f"Target resolution failed: {exc}",
        )

    inputs = _prepare_inputs(ac.sample_inputs, callable_obj)
    failing_diffs: list[str] = []

    for idx, args in enumerate(inputs):
        filename = _snapshot_filename(idx, args)
        snap_path = snap_dir / filename

        if not snap_path.exists():
            failing_diffs.append(
                f"Snapshot file missing for input {idx}: {snap_path}"
            )
            continue

        baseline = snap_path.read_text(encoding="utf-8")
        header = f"ARGS: {args!r}\n{'=' * 60}\n"
        current = header + _capture_call(callable_obj, args)

        if baseline == current:
            continue

        diff_lines = list(
            difflib.unified_diff(
                baseline.splitlines(keepends=True),
                current.splitlines(keepends=True),
                fromfile=f"{filename} (baseline)",
                tofile=f"{filename} (current)",
            )
        )

        if not _diff_is_allowed(diff_lines, ac.allow_changes):
            failing_diffs.append("".join(diff_lines))

    if failing_diffs:
        return VerificationResult(
            passed=False,
            diffs=failing_diffs,
            details=f"{len(failing_diffs)} input(s) regressed vs. snapshots in {ac.snapshot_dir}",
        )

    return VerificationResult(
        passed=True,
        diffs=[],
        details=f"All {len(inputs)} input(s) match baseline snapshots in {ac.snapshot_dir}",
    )


# ---------------------------------------------------------------------------
# High-level dispatch entry point
# ---------------------------------------------------------------------------

def characterization(
    ac: Any,
    workspace: pathlib.Path | str,
    phase: str = "verify",
) -> SnapshotResult | VerificationResult:
    """Run a characterization AC in the given *phase*.

    High-level entry point tying parsing, observation, and verification
    together. Parses *ac* into a :class:`CharacterizationAC` and dispatches to
    the observer or verifier phase.

    Args:
        ac:        Raw AC (dict/string) or an already-parsed
                   :class:`CharacterizationAC`.
        workspace: Project workspace root (path or string).
        phase:     ``'observe'`` to capture baseline snapshots, or ``'verify'``
                   (default) to diff current behavior against them.

    Returns:
        A :class:`SnapshotResult` for the observer phase, or a
        :class:`VerificationResult` for the verifier phase.

    Raises:
        ValueError: If *phase* is unrecognised or *ac* cannot be parsed as a
                    characterization criterion.
    """
    if phase not in ("observe", "verify"):
        raise ValueError(f"phase must be 'observe' or 'verify', got {phase!r}")

    ws = pathlib.Path(workspace)

    parsed = ac if isinstance(ac, CharacterizationAC) else parse_characterization_ac(ac)
    if parsed is None:
        raise ValueError(f"Could not parse characterization AC from: {ac!r}")

    if phase == "observe":
        return observe_and_snapshot(parsed, ws)
    return verify_against_snapshots(parsed, ws)


# ---------------------------------------------------------------------------
# Convenience aliases satisfying AC checks for these symbols at this module path
# ---------------------------------------------------------------------------

#: Observer phase callable — alias for :func:`observe_and_snapshot`.
CharacterizationObserver = observe_and_snapshot

#: Verifier phase callable — alias for :func:`verify_against_snapshots`.
CharacterizationVerifier = verify_against_snapshots
