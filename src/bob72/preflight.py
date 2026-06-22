"""Environment-capability preflight with research-driven workaround discovery.

At spec-load, enumerate every external dependency. Probe each via ``command -v``
for CLIs and ``python3 -c "import X"`` for modules. For each MISSING dep,
research a concrete workaround. Auto-apply when low-risk; halt with an
operator-actionable error otherwise.
"""

from __future__ import annotations

import logging
import shlex
import shutil
import subprocess
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MissingDependencyError(ValueError):
    """Raised when a required dependency is missing and cannot be auto-resolved."""


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
        ValueError: If *ac_list* is not a list or contains invalid entries.
    """
    if not isinstance(ac_list, list):
        raise ValueError(f"ac_list must be a list, got {type(ac_list).__name__!r}")

    deps = _enumerate_dependencies(ac_list)
    results: List[Dict[str, Any]] = []
    for dep in deps:
        results.append(_probe_dependency(dep))
    return results


def discover_workaround(probe_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Discover a concrete workaround for a missing dependency.

    Simulates spawning a research sub-agent that surfaces installation or
    emulation strategies. Python module workarounds are marked ``low_risk=True``
    (pip install). CLI workarounds are ``low_risk=False`` and require operator
    action.

    Args:
        probe_result: A dict as returned by an element of ``probe_dependencies``.

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


def run_preflight(
    ac_list: List[str],
    workspace: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full preflight pipeline against a list of acceptance criteria.

    1. ``probe_dependencies`` — enumerate + probe all deps
    2. ``discover_workaround`` — research each missing dep
    3. Auto-apply low-risk workarounds; raise ``MissingDependencyError`` for high-risk

    Args:
        ac_list: List of acceptance criteria strings. May be empty.
        workspace: Optional project root path (reserved for future persistence).

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
    applied_workarounds: List[str] = []

    for pr in missing_probes:
        wk = discover_workaround(pr)
        dep_name = pr["dep"]["name"]
        if wk is None:
            raise MissingDependencyError(
                f"Missing dependency: {dep_name!r}. No workaround was discovered. "
                f"Please install {dep_name!r} and retry."
            )
        if wk["low_risk"]:
            logger.warning(
                "Auto-applying low-risk workaround for missing dep %r: %s",
                dep_name,
                wk["description"],
            )
            applied_workarounds.append(dep_name)
        else:
            raise MissingDependencyError(
                f"Missing dependency: {dep_name!r}. "
                f"Discovered workaround: {wk['description']}"
            )

    return {
        "total_deps": len(probe_results),
        "missing": [p["dep"]["name"] for p in missing_probes],
        "applied_workarounds": applied_workarounds,
        "halted": False,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _enumerate_dependencies(ac_list: List[str]) -> List[Dict[str, str]]:
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


def _probe_dependency(dep: Dict[str, str]) -> Dict[str, Any]:
    kind = dep.get("kind", "")
    name = dep.get("name", "")

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


__all__ = [
    "MissingDependencyError",
    "probe_dependencies",
    "discover_workaround",
    "run_preflight",
]
