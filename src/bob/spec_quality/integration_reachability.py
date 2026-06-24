"""Integration-target reachability check at spec-load time.

For every ``integration: <dotted.module>`` acceptance-criterion entry,
verifies the target module is reachable BEFORE any code is generated:

  1. The module already exists as a file in the current workspace
     (``src/<path/to/module>.py`` or importable as-is).
  2. OR the module is itself a feature declared in the spec being planned
     (its ``integration`` AC entry names a module that will be created).

Unreachable targets are rejected with a structured error that names the
missing module and suggests the closest match by edit distance.
"""

from __future__ import annotations

import difflib
import importlib.util
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class UnreachableIntegrationError(Exception):
    """Raised when a spec contains an unreachable integration target."""

    def __init__(self, missing_module: str, feature_name: str = "", closest_match: str | None = None) -> None:
        self.missing_module = missing_module
        self.feature_name = feature_name
        self.closest_match = closest_match
        suggestion = f"; did you mean {closest_match!r}?" if closest_match else ""
        msg = f"Unreachable integration target: {missing_module!r}"
        if feature_name:
            msg = f"{msg} (in feature {feature_name!r})"
        super().__init__(msg + suggestion)


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_INTEGRATION_RE = re.compile(r"^integration\s*:\s*([\w./:-]+)", re.IGNORECASE)


def _extract_integration_targets(acceptance_criteria: list[str]) -> list[str]:
    """Return dotted module paths from ``integration: <path>`` ACs."""
    targets: list[str] = []
    for ac in acceptance_criteria:
        m = _INTEGRATION_RE.match(ac.strip())
        if m:
            targets.append(m.group(1).strip())
    return targets


# ---------------------------------------------------------------------------
# Reachability helpers
# ---------------------------------------------------------------------------

def _module_path_to_file_candidates(module: str, workspace: Path) -> list[Path]:
    """Return plausible filesystem locations for *module* under *workspace*."""
    # Convert dotted module (e.g. "bob.cli.plan") to slash path ("bob/cli/plan")
    rel = module.replace(".", "/")
    return [
        workspace / "src" / f"{rel}.py",
        workspace / f"{rel}.py",
        workspace / "src" / rel / "__init__.py",
        workspace / rel / "__init__.py",
    ]


def _module_exists_in_workspace(module: str, workspace: Path) -> bool:
    """Return True if *module* has a corresponding source file in *workspace*."""
    if any(p.exists() for p in _module_path_to_file_candidates(module, workspace)):
        return True
    # Recursive fallback: a module delivered at a non-canonical path (e.g.
    # seed-carried src/bob74/planner.py, or src/planner.py for a bare target)
    # is still reachable. Mirror the verifier's rglob resolution so the
    # reachability scorer and acceptance_criteria_met verifier converge — a
    # target the verifier accepts must not be gate-blocked here. Match on the
    # final dotted segment's leaf file anywhere under src/, tools/, tests/.
    leaf = module.replace(".", "/").rsplit("/", 1)[-1]
    if len(leaf) >= 4:
        for base in ("src", "tools", "tests"):
            root = workspace / base
            if root.is_dir() and next(root.rglob(f"{leaf}.py"), None) is not None:
                return True
    return False


def _module_is_importable(module: str) -> bool:
    """Return True if *module* is importable in the current Python environment."""
    # A relative module name (leading dot, e.g. an integration target like
    # '.claude.hooks.context_budget') makes importlib.util.find_spec raise a
    # plain ImportError ("no package specified ... required for relative module
    # names"), which is NOT a ModuleNotFoundError — it escaped the old narrow
    # except and crashed the whole run on startup (bob82 _recover_orphaned_
    # pending_features → reachability scoring). Reject such names up front, and
    # catch every importlib failure mode defensively: an unimportable/invalid
    # target is simply "not importable", never a hard crash of the scorer.
    if not module or module.startswith("."):
        return False
    try:
        spec = importlib.util.find_spec(module)
        return spec is not None
    except (ImportError, ValueError, TypeError, AttributeError, ModuleNotFoundError):
        return False
    except Exception:
        return False


def _collect_spec_modules(features: list[dict[str, Any]]) -> list[str]:
    """Return all integration-target modules declared anywhere in the spec."""
    result: list[str] = []
    for feat in features:
        ac_raw = feat.get("acceptance_criteria") or []
        if isinstance(ac_raw, str):
            ac_list: list[str] = [ac_raw]
        elif isinstance(ac_raw, list):
            ac_list = [str(c) for c in ac_raw]
        else:
            ac_list = []
        result.extend(_extract_integration_targets(ac_list))
    return result


def _closest_match(module: str, candidates: list[str]) -> str | None:
    """Return the closest match to *module* from *candidates* by edit distance."""
    if not candidates:
        return None
    matches = difflib.get_close_matches(module, candidates, n=1, cutoff=0.4)
    return matches[0] if matches else None


# ---------------------------------------------------------------------------
# Public data structures
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
                lines.append(
                    f"    Suggestion: did you mean {issue.closest_match!r}?"
                )
            lines.append("")
        return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Core check
# ---------------------------------------------------------------------------

def check_spec(
    features: list[dict[str, Any]],
    workspace: Path | str | None = None,
) -> ReachabilityResult:
    """Check every ``integration: <dotted.module>`` AC in *features*.

    For each integration target, the check passes if ANY of:
      - The module exists as a source file in *workspace*.
      - The module is importable in the current Python environment.
      - The module is itself declared as an integration target in
        another feature in the same spec (i.e., it will be created).

    Parameters
    ----------
    features:
        List of feature dicts, each with at least ``name`` and
        ``acceptance_criteria`` keys.
    workspace:
        Root directory of the project. Defaults to ``Path.cwd()``.

    Returns
    -------
    ReachabilityResult
        ``result.passed`` is True when all integration targets are reachable.
        Use ``result.format_report()`` to get a structured error message.
    """
    ws = Path(workspace) if workspace is not None else Path.cwd()
    result = ReachabilityResult()

    for feat in features:
        name = feat.get("name") or feat.get("title") or "(unnamed feature)"
        ac_raw = feat.get("acceptance_criteria") or []

        if isinstance(ac_raw, str):
            criteria: list[str] = [ac_raw]
        elif isinstance(ac_raw, list):
            criteria = [str(c) for c in ac_raw]
        else:
            criteria = []

        # A module is reachable via the spec if another feature (not this one)
        # also declares it as an integration target — meaning it will be created
        # by a sibling feature in the same planning batch.
        other_features = [f for f in features if f is not feat]
        sibling_modules = set(_collect_spec_modules(other_features))

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

            # Module is unreachable — suggest closest candidate.
            # Build candidate list: existing py files + sibling spec modules.
            existing_files = list(ws.rglob("*.py"))
            file_modules: list[str] = []
            for fp in existing_files:
                try:
                    rel = fp.relative_to(ws)
                    parts = list(rel.parts)
                    if parts[-1] == "__init__.py":
                        parts = parts[:-1]
                    else:
                        parts[-1] = parts[-1][:-3]  # strip .py
                    # Strip leading "src" component if present.
                    if parts and parts[0] == "src":
                        parts = parts[1:]
                    file_modules.append(".".join(parts))
                except ValueError:
                    pass

            candidates = list(set(file_modules) | (sibling_modules - {module}))
            suggestion = _closest_match(module, candidates)

            result.issues.append(
                ReachabilityIssue(
                    feature_name=str(name),
                    ac_index=idx,
                    criterion=stripped,
                    missing_module=module,
                    closest_match=suggestion,
                )
            )

    return result


# ---------------------------------------------------------------------------
# Public single-target helpers
# ---------------------------------------------------------------------------

def resolve_target(
    module: str,
    features: list[dict[str, Any]] | None = None,
    workspace: Path | str | None = None,
) -> Literal["in_workspace", "in_spec", "unreachable"]:
    """Classify a single integration *module* target.

    Returns one of:
    - ``"in_workspace"`` — a source file exists for the module, or it is importable.
    - ``"in_spec"``      — the module is declared as an integration target by
                           another feature in *features*.
    - ``"unreachable"``  — the module is not reachable by either means.

    The empty string always returns ``"unreachable"``.
    """
    if not module or not module.strip():
        return "unreachable"

    ws = Path(workspace) if workspace is not None else Path.cwd()
    feats = features or []

    if _module_exists_in_workspace(module, ws) or _module_is_importable(module):
        return "in_workspace"

    spec_modules = set(_collect_spec_modules(feats))
    if module in spec_modules:
        return "in_spec"

    return "unreachable"


def suggest_closest_match(
    module: str,
    features: list[dict[str, Any]] | None = None,
    workspace: Path | str | None = None,
) -> str | None:
    """Return the closest module name to *module* by Levenshtein distance.

    Searches workspace source files and spec-declared integration modules.
    Returns ``None`` when no close match is found.
    """
    ws = Path(workspace) if workspace is not None else Path.cwd()
    feats = features or []

    existing_files = list(ws.rglob("*.py"))
    file_modules: list[str] = []
    for fp in existing_files:
        try:
            rel = fp.relative_to(ws)
            parts = list(rel.parts)
            if parts[-1] == "__init__.py":
                parts = parts[:-1]
            else:
                parts[-1] = parts[-1][:-3]
            if parts and parts[0] == "src":
                parts = parts[1:]
            file_modules.append(".".join(parts))
        except ValueError:
            pass

    spec_modules = set(_collect_spec_modules(feats))
    candidates = list(set(file_modules) | spec_modules - {module})
    return _closest_match(module, candidates)


def raises_on_unreachable(
    module: str,
    features: list[dict[str, Any]] | None = None,
    workspace: Path | str | None = None,
) -> None:
    """Raise :class:`UnreachableIntegrationError` if *module* is unreachable.

    Convenience wrapper that combines :func:`resolve_target` and
    :func:`suggest_closest_match` into a single call that either succeeds
    silently or raises with a descriptive message.
    """
    status = resolve_target(module, features=features, workspace=workspace)
    if status == "unreachable":
        suggestion = suggest_closest_match(module, features=features, workspace=workspace)
        raise UnreachableIntegrationError(
            missing_module=module,
            closest_match=suggestion,
        )
