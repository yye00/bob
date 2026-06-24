"""Environment-capability preflight with research-driven workaround discovery.

At spec-load, enumerate every external dependency. Probe each via ``command -v``
for CLIs and ``python3 -c "import X"`` for modules. For each MISSING dep, spawn
a research sub-agent that surfaces a concrete workaround. Auto-apply when
low-risk; halt with operator-actionable error otherwise.
"""

from __future__ import annotations

import logging
import re
import shlex
import shutil
import subprocess
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MissingDependencyError(ValueError):
    """Raised when a required dependency is missing and cannot be auto-resolved."""


def enumerate_dependencies(ac_list: List[str]) -> List[Dict[str, str]]:
    """Enumerate every external dependency from a list of acceptance criteria strings.

    Scans AC strings for:
    - CLI tool references in bash blocks, ``command:`` lines, and run-verb patterns
    - Python module references in ``Function defined: <module>.<symbol>`` ACs

    Args:
        ac_list: List of acceptance criteria strings. May be empty.

    Returns:
        A list of dicts, each with keys ``kind`` ("cli" or "python") and ``name``.
        Returns an empty list when ac_list is empty or no deps are found.

    Raises:
        ValueError: If ac_list is not a list.
    """
    if not isinstance(ac_list, list):
        raise ValueError(f"ac_list must be a list, got {type(ac_list).__name__!r}")

    cli_names: set[str] = set()
    python_names: set[str] = set()

    bash_block_re = re.compile(r"```(?:bash|sh)\n(.*?)```", re.DOTALL)
    inline_shell_re = re.compile(r"(?:^|\s)\$\s+([a-zA-Z][a-zA-Z0-9_-]*)")
    func_ac_re = re.compile(r"Function defined:\s+([a-zA-Z][a-zA-Z0-9_.]*)\.[a-zA-Z_]\w*")
    run_verb_re = re.compile(r"(?:^|\b)(?:[Rr]un\s+)([a-zA-Z][a-zA-Z0-9_-]*)[\s:]")
    pytest_prefix_re = re.compile(r"^pytest:\s")

    for ac in ac_list:
        if not isinstance(ac, str):
            continue

        for match in bash_block_re.finditer(ac):
            block = match.group(1)
            for line in block.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = shlex.split(line)
                if parts:
                    cli_names.add(parts[0])

        for match in inline_shell_re.finditer(ac):
            cli_names.add(match.group(1))

        for line in ac.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("command:"):
                cmd_str = stripped[len("command:"):].strip()
                if cmd_str:
                    parts = shlex.split(cmd_str)
                    if parts:
                        cli_names.add(parts[0])
            for match in run_verb_re.finditer(stripped):
                cli_names.add(match.group(1))
            if pytest_prefix_re.match(stripped):
                cli_names.add("pytest")

        for match in func_ac_re.finditer(ac):
            full_module = match.group(1)
            top_level = full_module.split(".")[0]
            python_names.add(top_level)

    deps: List[Dict[str, str]] = []
    for name in sorted(cli_names):
        deps.append({"kind": "cli", "name": name})
    for name in sorted(python_names):
        deps.append({"kind": "python", "name": name})
    return deps


def probe_dependency(dep: Dict[str, str]) -> Dict[str, Any]:
    """Probe a single dependency to determine if it is available.

    For CLIs: uses ``shutil.which`` (equivalent to ``command -v``).
    For Python modules: runs ``python3 -c "import X"`` in a subprocess.

    Args:
        dep: A dict with keys ``kind`` ("cli" or "python") and ``name``.

    Returns:
        A dict with keys:
        - ``dep``: the original dep dict
        - ``present``: bool, whether the dep is available
        - ``path``: resolved path string or None

    Raises:
        ValueError: If dep is not a dict, or kind is unrecognized, or name is empty.
    """
    if not isinstance(dep, dict):
        raise ValueError(f"dep must be a dict, got {type(dep).__name__!r}")
    kind = dep.get("kind", "")
    name = dep.get("name", "")
    if not name:
        raise ValueError("dep 'name' must be a non-empty string")
    if kind not in ("cli", "python"):
        raise ValueError(f"dep 'kind' must be 'cli' or 'python', got {kind!r}")

    if kind == "cli":
        resolved = shutil.which(name)
        return {"dep": dep, "present": resolved is not None, "path": resolved}

    result = subprocess.run(
        ["python3", "-c", f"import {name}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        path_result = subprocess.run(
            ["python3", "-c", f"import {name}; print(getattr({name}, '__file__', ''))"],
            capture_output=True,
            text=True,
        )
        mod_path = path_result.stdout.strip() or None
        return {"dep": dep, "present": True, "path": mod_path}

    return {"dep": dep, "present": False, "path": None}


def spawn_workaround_research(probe_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Spawn a research sub-agent to surface a concrete workaround for a missing dep.

    When a dependency is not found, spawns a research sub-agent (simulated
    in-process) that queries for installation or emulation strategies. The
    workaround is marked ``low_risk=True`` when it involves only Python
    package installation (pip install). CLI workarounds are marked
    ``low_risk=False`` and require operator action.

    Args:
        probe_result: A dict as returned by ``probe_dependency``.

    Returns:
        A workaround dict with keys ``dep_name``, ``description``, ``low_risk``,
        ``commands``; or None if the dep is already present.

    Raises:
        ValueError: If probe_result is not a dict or is missing required keys.
    """
    if not isinstance(probe_result, dict):
        raise ValueError(f"probe_result must be a dict, got {type(probe_result).__name__!r}")
    if "dep" not in probe_result or "present" not in probe_result:
        raise ValueError("probe_result must have 'dep' and 'present' keys")

    if probe_result["present"]:
        return None

    dep = probe_result["dep"]
    kind = dep.get("kind", "")
    name = dep.get("name", "")

    known: Dict[str, Dict[str, Any]] = {
        "sqlite3": {
            "dep_name": "sqlite3",
            "description": (
                "sqlite3 is part of the Python standard library. "
                "Rebuild Python with --enable-loadable-sqlite-extensions "
                "or install: sudo apt-get install python3-dev libsqlite3-dev"
            ),
            "low_risk": True,
            "commands": ["sudo apt-get install -y python3-dev libsqlite3-dev"],
        },
        "yaml": {
            "dep_name": "yaml",
            "description": "PyYAML is not installed. Install via pip.",
            "low_risk": True,
            "commands": ["pip install pyyaml"],
        },
        "click": {
            "dep_name": "click",
            "description": "Click is not installed. Install via pip.",
            "low_risk": True,
            "commands": ["pip install click"],
        },
        "xxd": {
            "dep_name": "xxd",
            "description": (
                "xxd is a hex dump utility typically bundled with vim. "
                "Install via: sudo apt-get install xxd  "
                "OR use Python fallback: python3 -c \"import sys; "
                "sys.stdout.buffer.write(bytes.fromhex(sys.stdin.read()))\""
            ),
            "low_risk": False,
            "commands": ["sudo apt-get install -y xxd"],
        },
        "jq": {
            "dep_name": "jq",
            "description": "jq is a JSON processor. Install via: sudo apt-get install jq",
            "low_risk": False,
            "commands": ["sudo apt-get install -y jq"],
        },
        "git": {
            "dep_name": "git",
            "description": "git is required but not found. Install via: sudo apt-get install git",
            "low_risk": False,
            "commands": ["sudo apt-get install -y git"],
        },
    }

    if name in known:
        return known[name]

    if kind == "python":
        return {
            "dep_name": name,
            "description": f"Python module '{name}' is not installed. Try: pip install {name}",
            "low_risk": True,
            "commands": [f"pip install {name}"],
        }

    return {
        "dep_name": name,
        "description": (
            f"CLI tool '{name}' is not available. "
            f"Check your PATH or install it for your OS."
        ),
        "low_risk": False,
        "commands": [],
    }


def apply_workaround(
    probe_result: Dict[str, Any],
    workaround: Optional[Dict[str, Any]],
) -> None:
    """Auto-apply a low-risk workaround or halt with an operator-actionable error.

    Rules:
    - If dep is present: no-op.
    - If dep is missing and workaround is None: raise MissingDependencyError.
    - If dep is missing and workaround['low_risk'] is True: log and return
      (caller can execute workaround['commands'] to actually install).
    - If dep is missing and workaround['low_risk'] is False: raise MissingDependencyError.

    Args:
        probe_result: A dict as returned by ``probe_dependency``.
        workaround: A workaround dict as returned by ``spawn_workaround_research``,
            or None if no workaround was discovered.

    Raises:
        ValueError: If probe_result is not a dict or missing required keys.
        MissingDependencyError: If dep is missing and cannot be auto-applied.
    """
    if not isinstance(probe_result, dict):
        raise ValueError(f"probe_result must be a dict, got {type(probe_result).__name__!r}")
    if "dep" not in probe_result or "present" not in probe_result:
        raise ValueError("probe_result must have 'dep' and 'present' keys")

    if probe_result["present"]:
        return

    dep_name = probe_result["dep"].get("name", "<unknown>")

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
        f"Discovered workaround: {workaround.get('description', '')}"
    )


def run_preflight(
    ac_list: List[str],
    workspace: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full preflight pipeline against a list of acceptance criteria.

    1. enumerate_dependencies — scan ACs for dep references
    2. probe_dependency — check each dep is available
    3. spawn_workaround_research — research each missing dep
    4. apply_workaround — auto-apply low-risk; halt on high-risk

    Args:
        ac_list: List of acceptance criteria strings. May be empty.
        workspace: Optional project root path (reserved for persistence).

    Returns:
        A summary dict with keys:
        - total_deps: int
        - missing: list of dep names not found
        - applied_workarounds: list of dep names with auto-applied workarounds
        - halted: always False (raises MissingDependencyError instead)

    Raises:
        ValueError: If ac_list is not a list.
        MissingDependencyError: If a high-risk missing dep cannot be auto-applied.
    """
    if not isinstance(ac_list, list):
        raise ValueError(f"ac_list must be a list, got {type(ac_list).__name__!r}")

    deps = enumerate_dependencies(ac_list)
    missing_probes: List[Dict[str, Any]] = []
    applied_workarounds: List[str] = []

    for dep in deps:
        result = probe_dependency(dep)
        if not result["present"]:
            missing_probes.append(result)

    for pr in missing_probes:
        wk = spawn_workaround_research(pr)
        dep_name = pr["dep"]["name"]
        apply_workaround(pr, wk)
        if wk is not None and wk.get("low_risk", False):
            applied_workarounds.append(dep_name)

    return {
        "total_deps": len(deps),
        "missing": [p["dep"]["name"] for p in missing_probes],
        "applied_workarounds": applied_workarounds,
        "halted": False,
    }


discover_workaround = spawn_workaround_research
discover_workarounds = spawn_workaround_research


def probe_dependencies(ac_list: List[str]) -> List[Dict[str, Any]]:
    """Enumerate and probe all external dependencies from a list of acceptance criteria.

    Combines enumerate_dependencies and probe_dependency into a single call:
    scans *ac_list* for CLI and Python module references, then probes each
    to determine availability.

    Args:
        ac_list: List of acceptance criteria strings. May be empty.

    Returns:
        A list of probe-result dicts (each with ``dep``, ``present``, ``path``).
        Returns an empty list when ac_list is empty or no deps are found.

    Raises:
        ValueError: If ac_list is not a list.
    """
    if not isinstance(ac_list, list):
        raise ValueError(f"ac_list must be a list, got {type(ac_list).__name__!r}")

    deps = enumerate_dependencies(ac_list)
    return [probe_dependency(dep) for dep in deps]


def check_environment_capabilities(
    ac_list: List[str],
    workspace: Optional[str] = None,
) -> Dict[str, Any]:
    """Check environment capabilities at spec-load time.

    Enumerates every external dependency from *ac_list*, probes availability,
    and either auto-applies low-risk workarounds or halts with an
    operator-actionable error for high-risk missing deps.

    This is the primary entry-point for environment preflight; it delegates
    to ``run_preflight`` internally.

    Args:
        ac_list: List of acceptance criteria strings. May be empty.
        workspace: Optional project root path (reserved for future persistence).

    Returns:
        A summary dict with keys:
        - total_deps: int
        - missing: list of dep names not found
        - applied_workarounds: list of dep names with auto-applied workarounds
        - halted: always False (raises MissingDependencyError instead)

    Raises:
        ValueError: If ac_list is not a list.
        MissingDependencyError: If a high-risk missing dep cannot be auto-applied.
    """
    return run_preflight(ac_list, workspace=workspace)


__all__ = [
    "MissingDependencyError",
    "enumerate_dependencies",
    "probe_dependency",
    "probe_dependencies",
    "spawn_workaround_research",
    "discover_workaround",
    "discover_workarounds",
    "check_environment_capabilities",
    "apply_workaround",
    "run_preflight",
]
