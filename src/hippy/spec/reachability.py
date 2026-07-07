"""hippy.spec.reachability — integration-target reachability check at spec-load time.

Every ``integration: <dotted.module>`` acceptance-criterion implies the
generated code will be wired into that module.  Before any code is generated,
verify each target module is *reachable* — meaning ANY of:

  1. The module already exists as a source file in the current workspace
     (``src/<path>.py``, ``<path>.py`` or a package ``__init__.py``), OR is
     importable in the current Python environment.
  2. The module is itself declared as an integration target by another feature
     in the same spec (it will be created as part of the same planning batch).

Unreachable targets are rejected with a structured report that names the
missing module and suggests the closest match by edit distance.

Public API:
  :func:`check_integration_reachability` — check a whole spec (list of features).
  :func:`resolve_target_module`          — classify a single dotted module.
"""

from __future__ import annotations

import difflib
import importlib.util
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

_SENTINEL = object()

_INTEGRATION_RE = re.compile(r"^integration\s*:\s*([\w./:-]+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Result data structures
# ---------------------------------------------------------------------------

@dataclass
class ReachabilityIssue:
    """One unreachable integration-target finding."""

    feature_name: str
    ac_index: int
    criterion: str
    missing_module: str
    closest_match: str | None


@dataclass
class ReachabilityResult:
    """Aggregate reachability result for an entire spec."""

    issues: list[ReachabilityIssue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.issues) == 0

    def format_report(self) -> str:
        """Return a human-readable structured error report."""
        if self.passed:
            return "Integration-target reachability: PASSED"

        lines = ["Integration-target reachability: FAILED", ""]
        for issue in self.issues:
            lines.append(f"Feature: {issue.feature_name!r}")
            lines.append(
                f"  AC[{issue.ac_index}] {issue.criterion!r}: "
                f"unreachable module {issue.missing_module!r}"
            )
            if issue.closest_match:
                lines.append(f"    Suggestion: did you mean {issue.closest_match!r}?")
            lines.append("")
        return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _criteria_of(feature: dict[str, Any]) -> list[str]:
    ac_raw = feature.get("acceptance_criteria") or []
    if isinstance(ac_raw, str):
        return [ac_raw]
    if isinstance(ac_raw, list):
        return [str(c) for c in ac_raw]
    return []


def _extract_integration_targets(criteria: list[str]) -> list[str]:
    targets: list[str] = []
    for ac in criteria:
        m = _INTEGRATION_RE.match(ac.strip())
        if m:
            targets.append(m.group(1).strip())
    return targets


def _collect_spec_modules(features: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    for feat in features:
        result.extend(_extract_integration_targets(_criteria_of(feat)))
    return result


def _module_path_candidates(module: str, workspace: Path) -> list[Path]:
    rel = module.replace(".", "/")
    return [
        workspace / "src" / f"{rel}.py",
        workspace / f"{rel}.py",
        workspace / "src" / rel / "__init__.py",
        workspace / rel / "__init__.py",
    ]


def _module_exists_in_workspace(module: str, workspace: Path) -> bool:
    if any(p.exists() for p in _module_path_candidates(module, workspace)):
        return True
    # Fallback: a module delivered at a non-canonical path is still reachable.
    # Match the leaf file anywhere under src/, tools/, tests/.
    leaf = module.replace(".", "/").rsplit("/", 1)[-1]
    if len(leaf) >= 4:
        for base in ("src", "tools", "tests"):
            root = workspace / base
            if root.is_dir() and next(root.rglob(f"{leaf}.py"), None) is not None:
                return True
    return False


def _module_is_importable(module: str) -> bool:
    # Relative names (leading dot) make find_spec raise a bare ImportError, and
    # broken sibling packages can raise anything on import — treat all of these
    # as "not importable" rather than crashing the spec-load-time scorer.
    if not module or module.startswith("."):
        return False
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:
        return False


def _closest_match(module: str, candidates: list[str]) -> str | None:
    if not candidates:
        return None
    matches = difflib.get_close_matches(module, candidates, n=1, cutoff=0.4)
    return matches[0] if matches else None


def _workspace_module_names(workspace: Path) -> list[str]:
    names: list[str] = []
    for fp in workspace.rglob("*.py"):
        try:
            parts = list(fp.relative_to(workspace).parts)
        except ValueError:
            continue
        if parts and parts[-1] == "__init__.py":
            parts = parts[:-1]
        elif parts:
            parts[-1] = parts[-1][:-3]
        if parts and parts[0] == "src":
            parts = parts[1:]
        if parts:
            names.append(".".join(parts))
    return names


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_target_module(
    module: str,
    features: list[dict[str, Any]] | None = None,
    workspace: Path | str | None = None,
) -> Literal["in_workspace", "in_spec", "unreachable"]:
    """Classify a single integration *module* target.

    Returns:
      - ``"in_workspace"`` — a source file exists for the module, or it is
        importable in the current environment.
      - ``"in_spec"``      — the module is declared as an integration target by
        a feature in *features* (it will be created in the same plan).
      - ``"unreachable"``  — neither of the above.

    An empty / whitespace-only *module* always returns ``"unreachable"``.
    """
    if not module or not module.strip():
        return "unreachable"

    module = module.strip()
    ws = Path(workspace) if workspace is not None else Path.cwd()

    if _module_exists_in_workspace(module, ws) or _module_is_importable(module):
        return "in_workspace"

    if module in set(_collect_spec_modules(features or [])):
        return "in_spec"

    return "unreachable"


def check_integration_reachability(
    features: Any = _SENTINEL,
    workspace: Path | str | None = None,
    *,
    reject_on_failure: bool = False,
) -> ReachabilityResult:
    """Check every ``integration: <dotted.module>`` AC in *features*.

    Parameters
    ----------
    features:
        List of feature dicts, each with at least ``name`` and
        ``acceptance_criteria`` keys.  Must be a list — any other type
        (including ``None``) raises :exc:`ValueError`.  Defaults to an empty
        list when omitted.
    workspace:
        Root directory of the project.  Defaults to ``Path.cwd()``.
    reject_on_failure:
        When ``True``, raise :exc:`ValueError` if any integration target is
        unreachable.  Default is ``False`` (returns the result without raising).

    Returns
    -------
    ReachabilityResult
        ``result.passed`` is ``True`` when all integration targets are
        reachable.  Use ``result.format_report()`` for a structured message.

    Raises
    ------
    ValueError
        If *features* is not a list, or if *reject_on_failure* is ``True`` and
        any integration target is unreachable.
    """
    if features is not _SENTINEL and not isinstance(features, list):
        raise ValueError(f"features must be a list, got {type(features).__name__!r}")

    feat_list: list[dict[str, Any]] = [] if features is _SENTINEL else features
    ws = Path(workspace) if workspace is not None else Path.cwd()

    result = ReachabilityResult()

    for feat in feat_list:
        name = feat.get("name") or feat.get("title") or "(unnamed feature)"
        criteria = _criteria_of(feat)

        # Sibling modules: integration targets declared by OTHER features in the
        # batch — these will be created as part of the same plan.
        others = [f for f in feat_list if f is not feat]
        sibling_modules = set(_collect_spec_modules(others))

        for idx, ac in enumerate(criteria):
            stripped = ac.strip()
            m = _INTEGRATION_RE.match(stripped)
            if not m:
                continue

            module = m.group(1).strip()
            if (
                _module_exists_in_workspace(module, ws)
                or _module_is_importable(module)
                or module in sibling_modules
            ):
                continue

            candidates = list(
                set(_workspace_module_names(ws)) | (sibling_modules - {module})
            )
            result.issues.append(
                ReachabilityIssue(
                    feature_name=str(name),
                    ac_index=idx,
                    criterion=stripped,
                    missing_module=module,
                    closest_match=_closest_match(module, candidates),
                )
            )

    if reject_on_failure and not result.passed:
        raise ValueError(result.format_report())

    return result
