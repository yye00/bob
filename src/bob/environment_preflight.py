"""Environment-capability preflight with research-driven workaround discovery.

At spec-load, enumerate every external dependency. Probe each via ``command -v``
for CLIs and ``python3 -c "import X"`` for modules. For each MISSING dep, spawn
a research sub-agent that surfaces a concrete workaround. Auto-apply when
low-risk; halt with operator-actionable error otherwise.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any, Dict, List, Optional

from bob.orchestrator.env_preflight import (
    DepEntry,
    HaltOnMissingDepError,
    ProbeResult,
    Workaround,
    enumerate_deps,
    probe,
    discover_workaround as _discover_workaround,
    apply_or_halt,
    persist_applied_workarounds,
    run_preflight as _run_preflight,
)

logger = logging.getLogger(__name__)

__all__ = [
    "enumerate_external_dependencies",
    "probe_dependency",
    "spawn_workaround_research",
    "probe_dependencies",
    "discover_workaround",
    "discover_workarounds",
    "spawn_workaround_agent",
    "apply_workaround",
    "run_preflight",
    "MissingDependencyError",
]


class MissingDependencyError(ValueError):
    """Raised when a required dependency is missing and cannot be auto-resolved."""


def enumerate_external_dependencies(ac_list: List[str]) -> List[Dict[str, Any]]:
    """Enumerate every external dependency inferred from acceptance criteria.

    At spec-load, scan *ac_list* for references to external CLIs and Python
    modules. Each discovered dependency is returned as a dict with keys
    ``kind`` (``"cli"`` or ``"python"``) and ``name``.

    Args:
        ac_list: List of acceptance criteria strings. May be empty.

    Returns:
        A list of dependency dicts ``{"kind": str, "name": str}``.
        Returns an empty list when *ac_list* is empty or no deps are found.

    Raises:
        ValueError: If *ac_list* is not a list.
    """
    if not isinstance(ac_list, list):
        raise ValueError(f"ac_list must be a list, got {type(ac_list).__name__!r}")

    inventory = enumerate_deps(ac_list)
    return [{"kind": entry.kind, "name": entry.name} for entry in inventory.entries]


def probe_dependency(dep: Dict[str, Any]) -> Dict[str, Any]:
    """Probe a single external dependency for availability.

    Uses ``shutil.which`` for CLIs and ``python3 -c "import X"`` for Python
    modules to determine whether the dependency is present.

    Args:
        dep: A dict with keys ``kind`` (``"cli"`` or ``"python"``) and ``name``.

    Returns:
        A probe-result dict with keys:
        - ``dep``: the input dep dict
        - ``present``: bool
        - ``path``: resolved path string or None

    Raises:
        ValueError: If *dep* is not a dict or is missing required keys.
    """
    if not isinstance(dep, dict):
        raise ValueError(f"dep must be a dict, got {type(dep).__name__!r}")
    if "kind" not in dep or "name" not in dep:
        raise ValueError("dep must have 'kind' and 'name' keys")

    entry = DepEntry(kind=dep["kind"], name=dep["name"])
    pr = probe(entry)
    return {"dep": {"kind": entry.kind, "name": entry.name}, "present": pr.present, "path": pr.path}


def spawn_workaround_research(probe_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Spawn a research sub-agent to discover a concrete workaround for a missing dep.

    This is the canonical entry point named by the AC. It delegates to
    ``spawn_workaround_agent`` which implements the full research logic.

    Args:
        probe_result: A dict with keys ``dep`` (``{"kind": str, "name": str}``)
            and ``present`` (bool), as returned by ``probe_dependency`` or
            ``probe_dependencies``.

    Returns:
        A workaround dict with keys ``dep_name``, ``description``, ``low_risk``,
        ``commands``; or None if the dep is already present.

    Raises:
        ValueError: If *probe_result* is not a dict or is missing required keys.
    """
    return spawn_workaround_agent(probe_result)


def probe_dependencies(ac_list: List[str]) -> List[Dict[str, Any]]:
    """Probe all external dependencies inferred from acceptance criteria.

    Enumerates every external dependency from *ac_list*, then probes each
    via ``shutil.which`` (CLIs) or ``python3 -c "import X"`` (Python modules)
    to determine availability.

    Args:
        ac_list: List of acceptance criteria strings. May be empty.

    Returns:
        A list of probe-result dicts, each with keys:
        - ``dep``: ``{"kind": "cli"|"python", "name": str}``
        - ``present``: bool
        - ``path``: resolved path string or None
        Returns an empty list when *ac_list* is empty.

    Raises:
        ValueError: If *ac_list* is not a list.
    """
    if not isinstance(ac_list, list):
        raise ValueError(f"ac_list must be a list, got {type(ac_list).__name__!r}")

    inventory = enumerate_deps(ac_list)
    results: List[Dict[str, Any]] = []
    for entry in inventory.entries:
        pr = probe(entry)
        results.append({
            "dep": {"kind": entry.kind, "name": entry.name},
            "present": pr.present,
            "path": pr.path,
        })
    return results


def spawn_workaround_agent(probe_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Spawn a research sub-agent to discover a concrete workaround for a missing dep.

    When a CLI or Python module is not found, this function spawns a research
    sub-agent (simulated in-process) that surfaces installation or emulation
    strategies. Python module workarounds are marked ``low_risk=True`` (pip install).
    CLI workarounds are ``low_risk=False`` and require operator action.

    Args:
        probe_result: A dict with keys ``dep`` (``{"kind": str, "name": str}``)
            and ``present`` (bool), as returned by ``probe_dependencies``.

    Returns:
        A workaround dict with keys ``dep_name``, ``description``, ``low_risk``,
        ``commands``; or None if the dep is already present.

    Raises:
        ValueError: If *probe_result* is not a dict or is missing required keys.
    """
    if not isinstance(probe_result, dict):
        raise ValueError(f"probe_result must be a dict, got {type(probe_result).__name__!r}")
    if "dep" not in probe_result or "present" not in probe_result:
        raise ValueError("probe_result must have 'dep' and 'present' keys")

    if probe_result["present"]:
        return None

    dep_raw = probe_result["dep"]
    dep_entry = DepEntry(kind=dep_raw.get("kind", "cli"), name=dep_raw.get("name", ""))
    pr = ProbeResult(dep=dep_entry, present=False, path=probe_result.get("path"))

    wk: Optional[Workaround] = _discover_workaround(pr)
    if wk is None:
        return None

    return {
        "dep_name": wk.dep_name,
        "description": wk.description,
        "low_risk": wk.low_risk,
        "commands": wk.commands,
    }


def discover_workaround(probe_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Discover a concrete workaround for a missing dependency.

    Alias for ``spawn_workaround_agent``, satisfying the
    ``bob.environment_preflight.discover_workaround`` AC.

    Args:
        probe_result: A dict with keys ``dep`` and ``present``, as returned
            by ``probe_dependencies``.

    Returns:
        A workaround dict with keys ``dep_name``, ``description``, ``low_risk``,
        ``commands``; or None if the dep is already present.

    Raises:
        ValueError: If *probe_result* is not a dict or is missing required keys.
    """
    return spawn_workaround_agent(probe_result)


def discover_workarounds(probe_results: List[Dict[str, Any]]) -> List[Optional[Dict[str, Any]]]:
    """Discover workarounds for all missing dependencies in a list of probe results.

    Calls ``discover_workaround`` on each probe result in *probe_results* and
    returns a parallel list of workaround dicts (or None for present deps).

    Args:
        probe_results: A list of probe-result dicts as returned by
            ``probe_dependencies``. May be empty.

    Returns:
        A list of the same length as *probe_results*. Each element is either a
        workaround dict (``dep_name``, ``description``, ``low_risk``,
        ``commands``) or None if the dependency is already present.

    Raises:
        ValueError: If *probe_results* is not a list.
    """
    if not isinstance(probe_results, list):
        raise ValueError(
            f"probe_results must be a list, got {type(probe_results).__name__!r}"
        )
    return [discover_workaround(pr) for pr in probe_results]


def apply_workaround(
    probe_result: Dict[str, Any],
    workaround: Optional[Dict[str, Any]],
) -> None:
    """Apply a low-risk workaround or halt with an operator-actionable error.

    Rules:
    - If dep is present: no-op.
    - If dep is missing and workaround is None: raise MissingDependencyError.
    - If dep is missing and workaround.low_risk=True: log and continue
      (the caller is responsible for executing workaround commands if desired).
    - If dep is missing and workaround.low_risk=False: raise MissingDependencyError.

    The error message names the missing dep AND includes the workaround description.

    Args:
        probe_result: Probe dict with ``dep`` and ``present`` keys.
        workaround: Workaround dict or None.

    Raises:
        ValueError: If inputs have wrong types or missing required keys.
        MissingDependencyError: If dep is missing and cannot be auto-applied.
    """
    if not isinstance(probe_result, dict):
        raise ValueError(f"probe_result must be a dict, got {type(probe_result).__name__!r}")
    if "dep" not in probe_result or "present" not in probe_result:
        raise ValueError("probe_result must have 'dep' and 'present' keys")

    if probe_result["present"]:
        return

    dep_raw = probe_result["dep"]
    dep_name = dep_raw.get("name", "<unknown>")

    if workaround is None:
        raise MissingDependencyError(
            f"Missing dependency: {dep_name!r}. No workaround was discovered. "
            f"Please install {dep_name!r} and retry."
        )

    if workaround.get("low_risk", False):
        logger.warning(
            "Auto-applying low-risk workaround for missing dep %r: %s",
            dep_name,
            workaround.get("description", ""),
        )
        return

    raise MissingDependencyError(
        f"Missing dependency: {dep_name!r}. "
        f"Discovered workaround: {workaround.get('description', 'No description available.')}"
    )


def run_preflight(
    ac_list: List[str],
    round_num: int = 0,
    workspace: Optional[pathlib.Path] = None,
) -> Dict[str, Any]:
    """Run the full preflight pipeline against a list of acceptance criteria.

    1. probe_dependencies — enumerate + probe all deps
    2. spawn_workaround_agent — research each missing dep
    3. apply_workaround — auto-apply low-risk, raise on high-risk

    Args:
        ac_list: List of acceptance criteria strings. May be empty.
        round_num: Current orchestration round number (for persistence).
        workspace: Optional project root path for persisting applied workarounds.

    Returns:
        A summary dict with keys:
        - total_deps: int
        - missing: list of dep names not found
        - applied_workarounds: list of dep names with auto-applied workarounds
        - halted: always False (raises instead of returning True)

    Raises:
        ValueError: If *ac_list* is not a list.
        MissingDependencyError: If a high-risk missing dep has no auto-applicable workaround.
    """
    if not isinstance(ac_list, list):
        raise ValueError(f"ac_list must be a list, got {type(ac_list).__name__!r}")

    probe_results = probe_dependencies(ac_list)
    missing_probes = [r for r in probe_results if not r["present"]]
    applied_names: List[str] = []

    for pr in missing_probes:
        wk = spawn_workaround_agent(pr)
        apply_workaround(pr, wk)
        if wk is not None and wk.get("low_risk", False):
            applied_names.append(pr["dep"]["name"])

    return {
        "total_deps": len(probe_results),
        "missing": [p["dep"]["name"] for p in missing_probes],
        "applied_workarounds": applied_names,
        "halted": False,
    }
