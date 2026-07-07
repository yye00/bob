"""Scoped incremental build with compiler-warning baseline attribution.

Feature f3a62a46-d21b-4708-9331-79886d1411d2

Bob has no notion of compiler warnings and never builds C++. The Python analog
— per-feature pytest scoping so a feature never runs the whole world — has no
C++ counterpart, and a naive full RCCL build recompiles every arch on every
feature. This module extends the ``build:`` gate with two capabilities:

(a) **Scoped incremental targets.** Given the translation units a feature
    edited plus a ninja dependency graph (``target: [dependents]``), resolve the
    minimal set of ninja targets that depend on the edited TUs, so the build
    recompiles only what changed rather than the whole tree. This mirrors
    :mod:`bob.scoped_pytest_runner` scoping pytest to a feature's own subtree.
    ``ninja -d explain`` output is inspected to warn on spurious full rebuilds,
    a common HIP depfile problem.

(b) **Compiler-warning baseline attribution.** Compile the feature's edited TUs
    with ``-Wall -Wextra -Werror=return-type -Werror=uninitialized`` and diff the
    resulting warnings against a baseline warning-set captured at bootstrap. Only
    NEW warnings introduced on the CHANGED files demote confidence; pre-existing
    brownfield warnings never scapegoat the current feature. This mirrors bob's
    ``tests_pass_regression_vs_baseline`` attribution, but for the compiler
    diagnostic stream.

Public API
----------
``incremental_build_targets(edited_translation_units, *, dependency_graph, ninja_explain_output=None)``
    Resolve the scoped set of ninja targets for a feature's edits.

``attribute_new_warnings_vs_baseline(current_warnings, baseline_warnings, *, changed_files=None)``
    Diff the compiler diagnostic stream against the baseline and attribute only
    genuinely new warnings on changed files to the current feature.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

__all__ = [
    "BuildPlan",
    "WarningAttribution",
    "incremental_build_targets",
    "attribute_new_warnings_vs_baseline",
    "WARNING_FLAGS",
]

# Compiler flags applied to the feature's edited TUs. -Werror on the two flags
# most likely to reflect real defects introduced by an edit; -Wall/-Wextra as a
# soft signal that only demotes confidence (see attribution below).
WARNING_FLAGS = (
    "-Wall",
    "-Wextra",
    "-Werror=return-type",
    "-Werror=uninitialized",
)

# Heuristic: ninja -d explain lines beyond this count on an incremental build
# indicate the dependency graph forced a near-full rebuild (HIP depfile bug).
_SPURIOUS_REBUILD_LINE_THRESHOLD = 50

_WARNING_FILE_RE = re.compile(r"^\s*([^\s:][^:]*):\d+:\d+:\s*warning:", re.MULTILINE)


@dataclass
class BuildPlan:
    """Resolved incremental build scope for a feature's edits."""

    edited_translation_units: list[str]
    targets: list[str]
    is_full_rebuild: bool = False
    spurious_rebuild_warning: str | None = None


@dataclass
class WarningAttribution:
    """Result of diffing the compiler diagnostic stream against baseline."""

    new_warnings: list[str] = field(default_factory=list)
    confidence_demoted: bool = False


# ---------------------------------------------------------------------------
# Input normalization
# ---------------------------------------------------------------------------


def _as_line_list(value: object, *, name: str) -> list[str]:
    """Coerce raw compiler output (str) or a sequence of lines into a list[str]."""
    if value is None:
        raise ValueError(f"{name} must not be None")
    if isinstance(value, str):
        return [ln for ln in value.splitlines() if ln.strip()]
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError(f"{name} entries must be strings, got {type(item)!r}")
            if item.strip():
                out.append(item)
        return out
    raise ValueError(f"{name} must be a string or list of strings, got {type(value)!r}")


def _warning_file(line: str) -> str | None:
    """Extract the source file path a warning line refers to, if any."""
    match = _WARNING_FILE_RE.match(line)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# (a) Scoped incremental targets
# ---------------------------------------------------------------------------


def incremental_build_targets(
    edited_translation_units: Sequence[str],
    *,
    dependency_graph: Mapping[str, Iterable[str]] | None = None,
    ninja_explain_output: str | None = None,
) -> BuildPlan:
    """Resolve the minimal set of ninja targets that depend on the edited TUs.

    This is the C++ analog of scoping pytest to a feature's own subtree: instead
    of ``ninja`` (which rebuilds the whole tree), the build only refreshes the
    targets whose inputs include one of the feature's edited translation units.

    Args:
        edited_translation_units: Paths of the TUs the feature edited.
        dependency_graph: Mapping of ``source_file -> [dependent ninja targets]``.
            Defaults to an empty graph.
        ninja_explain_output: Optional captured ``ninja -d explain`` text. When a
            large number of explain lines is seen on an incremental build, a
            spurious full-rebuild warning is emitted (HIP depfile problem).

    Returns:
        A :class:`BuildPlan` with the deduplicated, sorted target list.

    Raises:
        ValueError: If *edited_translation_units* is not a list/tuple of strings,
            or *dependency_graph* is not a mapping.
    """
    if edited_translation_units is None or not isinstance(
        edited_translation_units, (list, tuple)
    ):
        raise ValueError(
            "edited_translation_units must be a list or tuple of strings"
        )
    for tu in edited_translation_units:
        if not isinstance(tu, str):
            raise ValueError(
                f"edited_translation_units entries must be strings, got {type(tu)!r}"
            )

    if dependency_graph is None:
        dependency_graph = {}
    if not isinstance(dependency_graph, Mapping):
        raise ValueError("dependency_graph must be a mapping")

    edited = list(edited_translation_units)

    targets: set[str] = set()
    for tu in edited:
        dependents = dependency_graph.get(tu)
        if dependents:
            targets.update(dependents)
        else:
            # No known dependents: schedule the TU itself so the build is never
            # a silent no-op that skips genuinely-edited code.
            targets.add(tu)

    spurious = None
    if ninja_explain_output and edited:
        explain_lines = [
            ln for ln in ninja_explain_output.splitlines() if "ninja explain" in ln
        ]
        if len(explain_lines) > _SPURIOUS_REBUILD_LINE_THRESHOLD:
            spurious = (
                f"Spurious full rebuild suspected: ninja -d explain emitted "
                f"{len(explain_lines)} explain lines for {len(edited)} edited TU(s) "
                f"(likely a HIP depfile problem forcing recompilation of "
                f"unrelated targets)."
            )

    return BuildPlan(
        edited_translation_units=edited,
        targets=sorted(targets),
        is_full_rebuild=False,
        spurious_rebuild_warning=spurious,
    )


# ---------------------------------------------------------------------------
# (b) Compiler-warning baseline attribution
# ---------------------------------------------------------------------------


def attribute_new_warnings_vs_baseline(
    current_warnings: Sequence[str] | str,
    baseline_warnings: Sequence[str] | str,
    *,
    changed_files: Sequence[str] | None = None,
) -> WarningAttribution:
    """Diff the compiler diagnostic stream against a bootstrap baseline.

    Only warnings that are (1) absent from the baseline and (2) attached to a
    file the feature actually changed are attributed to the current feature.
    This mirrors ``tests_pass_regression_vs_baseline``: pre-existing brownfield
    warnings never scapegoat the current feature, and warnings that appear on
    files this feature never touched are not its fault.

    Args:
        current_warnings: Compiler output after building the feature — either a
            raw string or a list of warning lines.
        baseline_warnings: Warning-set captured at bootstrap, same format.
        changed_files: Files the feature edited. When provided, new warnings are
            filtered to those on these files. When None, all new warnings count.

    Returns:
        A :class:`WarningAttribution`. ``confidence_demoted`` is True when at
        least one genuinely-new attributable warning exists.

    Raises:
        ValueError: If *current_warnings* or *baseline_warnings* is None/wrong
            type, or *changed_files* is not a list/tuple.
    """
    current = _as_line_list(current_warnings, name="current_warnings")
    baseline_set = set(_as_line_list(baseline_warnings, name="baseline_warnings"))

    if changed_files is not None and not isinstance(changed_files, (list, tuple)):
        raise ValueError("changed_files must be a list or tuple of strings")
    changed_set = set(changed_files) if changed_files else None

    new_warnings: list[str] = []
    for line in current:
        if line in baseline_set:
            continue  # brownfield — never scapegoat the current feature
        if changed_set is not None:
            wfile = _warning_file(line)
            if wfile is not None and wfile not in changed_set:
                continue  # warning on a file this feature did not touch
            if wfile is None:
                # Unparseable file → cannot attribute to a changed file; skip
                # when scoping was requested to avoid false blame.
                continue
        new_warnings.append(line)

    return WarningAttribution(
        new_warnings=new_warnings,
        confidence_demoted=bool(new_warnings),
    )
