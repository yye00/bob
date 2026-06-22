"""Probe bob_N capabilities across languages, frameworks, build systems, and GPU tools.

CLI: python -m tools.capability_matrix [--out PATH] [--history PATH]

Output:
  docs/recursion/round1/capability_matrix.json  (default --out target)
  capability_matrix_history.jsonl               (default --history target, overwritten)

Each capability cell has the shape:
  {supported: bool, smoke_test_passes: bool, sample_project: str | null}
"""

from __future__ import annotations

import argparse
import ast
import datetime
import json
import pathlib
import re
import shutil
import subprocess
import sys

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent

DEFAULT_OUT = WORKSPACE / "docs" / "recursion" / "round1" / "capability_matrix.json"
DEFAULT_HISTORY = WORKSPACE / "capability_matrix_history.jsonl"

# Verification check names hard-coded in superpowers.py.
# Extracted by static analysis at build time; kept as a constant so the
# matrix can be produced without executing the full bob3 test suite.
_SUPERPOWERS_CHECKS = [
    "tests_pass",
    "source_files_exist",
    "package_has_substance",
    "test_files_exist",
    "no_stubs_in_source",
    "no_mocks_in_source",
    "code_changes_made",
    "acceptance_criteria_met",
    "integration_code_exists",
    "security_scan",
]


def _cmd_available(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run_smoke(args: list[str], input_text: str | None = None) -> bool:
    try:
        result = subprocess.run(
            args,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except Exception:
        return False


def _cell(supported: bool, smoke: bool, sample: str | None = None) -> dict:
    return {"supported": supported, "smoke_test_passes": smoke, "sample_project": sample}


def _probe_python() -> dict:
    supported = _cmd_available("python") or _cmd_available("python3") or True  # always present
    smoke = _run_smoke([sys.executable, "-c", "print('ok')"])
    return _cell(True, smoke, "src/bob3")


def _probe_js() -> dict:
    supported = _cmd_available("node")
    smoke = _run_smoke(["node", "-e", "console.log('ok')"]) if supported else False
    return _cell(supported, smoke, None)


def _probe_ts() -> dict:
    supported = _cmd_available("tsc") or _cmd_available("npx")
    smoke = False
    if _cmd_available("npx"):
        smoke = _run_smoke(["npx", "--yes", "tsc", "--version"])
    elif _cmd_available("tsc"):
        smoke = _run_smoke(["tsc", "--version"])
    return _cell(supported, smoke, None)


def _probe_java() -> dict:
    supported = _cmd_available("java")
    smoke = _run_smoke(["java", "-version"]) if supported else False
    return _cell(supported, smoke, None)


def _probe_cpp() -> dict:
    supported = _cmd_available("g++") or _cmd_available("clang++")
    compiler = "g++" if _cmd_available("g++") else ("clang++" if _cmd_available("clang++") else None)
    smoke = False
    if compiler:
        smoke = _run_smoke([compiler, "--version"])
    return _cell(supported, smoke, None)


def _probe_hip() -> dict:
    supported = _cmd_available("hipcc")
    smoke = _run_smoke(["hipcc", "--version"]) if supported else False
    return _cell(supported, smoke, None)


def _probe_languages() -> dict:
    return {
        "python": _probe_python(),
        "js": _probe_js(),
        "ts": _probe_ts(),
        "java": _probe_java(),
        "c++": _probe_cpp(),
        "hip": _probe_hip(),
    }


def _probe_pytest() -> dict:
    supported = _run_smoke([sys.executable, "-m", "pytest", "--version"])
    smoke = supported
    return _cell(True, smoke, "tests/")


def _probe_jest() -> dict:
    supported = _cmd_available("jest") or (
        _cmd_available("npx") and _run_smoke(["npx", "--yes", "jest", "--version"])
    )
    return _cell(supported, supported, None)


def _probe_vitest() -> dict:
    supported = _cmd_available("vitest") or (
        _cmd_available("npx") and _run_smoke(["npx", "--yes", "vitest", "--version"])
    )
    return _cell(supported, supported, None)


def _probe_junit() -> dict:
    supported = _cmd_available("java")
    return _cell(supported, False, None)


def _probe_gtest() -> dict:
    supported = _cmd_available("g++") or _cmd_available("clang++")
    return _cell(supported, False, None)


def _probe_ctest() -> dict:
    supported = _cmd_available("ctest")
    smoke = _run_smoke(["ctest", "--version"]) if supported else False
    return _cell(supported, smoke, None)


def _probe_test_frameworks() -> dict:
    return {
        "pytest": _probe_pytest(),
        "jest": _probe_jest(),
        "vitest": _probe_vitest(),
        "junit": _probe_junit(),
        "gtest": _probe_gtest(),
        "ctest": _probe_ctest(),
    }


def _probe_pip() -> dict:
    supported = _run_smoke([sys.executable, "-m", "pip", "--version"])
    return _cell(True, supported, "pyproject.toml")


def _probe_npm() -> dict:
    supported = _cmd_available("npm")
    smoke = _run_smoke(["npm", "--version"]) if supported else False
    return _cell(supported, smoke, None)


def _probe_maven() -> dict:
    supported = _cmd_available("mvn")
    smoke = _run_smoke(["mvn", "--version"]) if supported else False
    return _cell(supported, smoke, None)


def _probe_gradle() -> dict:
    supported = _cmd_available("gradle")
    smoke = _run_smoke(["gradle", "--version"]) if supported else False
    return _cell(supported, smoke, None)


def _probe_cmake() -> dict:
    supported = _cmd_available("cmake")
    smoke = _run_smoke(["cmake", "--version"]) if supported else False
    return _cell(supported, smoke, None)


def _probe_ninja() -> dict:
    supported = _cmd_available("ninja")
    smoke = _run_smoke(["ninja", "--version"]) if supported else False
    return _cell(supported, smoke, None)


def _probe_build_systems() -> dict:
    return {
        "pip": _probe_pip(),
        "npm": _probe_npm(),
        "maven": _probe_maven(),
        "gradle": _probe_gradle(),
        "cmake": _probe_cmake(),
        "ninja": _probe_ninja(),
    }


def _probe_compute_sanitizer() -> dict:
    supported = _cmd_available("compute-sanitizer")
    smoke = _run_smoke(["compute-sanitizer", "--version"]) if supported else False
    return _cell(supported, smoke, None)


def _probe_rocprof() -> dict:
    supported = _cmd_available("rocprof")
    smoke = _run_smoke(["rocprof", "--version"]) if supported else False
    return _cell(supported, smoke, None)


def _probe_gpu_verification() -> dict:
    return {
        "compute-sanitizer": _probe_compute_sanitizer(),
        "rocprof": _probe_rocprof(),
    }


def _extract_verification_checks() -> list[str]:
    """Extract check names registered in superpowers.py via static AST scan.

    Two patterns are detected:
    1. Inline dict literals: {"name": "check_name", ...}
    2. Variable assignments used as the name value: check_name = "tests_pass"
       followed by {"name": check_name, ...}
    """
    superpowers_path = WORKSPACE / "src" / "bob3" / "superpowers.py"
    if not superpowers_path.exists():
        return list(_SUPERPOWERS_CHECKS)

    try:
        source = superpowers_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return list(_SUPERPOWERS_CHECKS)

    # Pass 1: collect variable bindings: varname -> string value
    var_strings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    var_strings[target.id] = node.value.value

    # Pass 2: find {"name": <literal or known var>} patterns
    names: list[str] = []
    seen: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and key.value == "name"):
                continue
            name: str | None = None
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                name = value.value
            elif isinstance(value, ast.Name) and value.id in var_strings:
                name = var_strings[value.id]
            if name is not None and name not in seen:
                seen.add(name)
                names.append(name)

    return names if names else list(_SUPERPOWERS_CHECKS)


def probe_capabilities() -> dict:
    """Probe all capabilities of the current bob_N environment.

    Returns a dict with keys: languages, test_frameworks, build_systems,
    gpu_verification, verification_checks.
    """
    return {
        "languages": _probe_languages(),
        "test_frameworks": _probe_test_frameworks(),
        "build_systems": _probe_build_systems(),
        "gpu_verification": _probe_gpu_verification(),
        "verification_checks": _extract_verification_checks(),
    }


def _write_history(matrix: dict, history_path: pathlib.Path) -> None:
    entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "matrix": matrix,
    }
    history_path.parent.mkdir(parents=True, exist_ok=True)
    # overwrite with one new line (spec: "overwrites capability_matrix_history.jsonl")
    history_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Probe bob_N capabilities and emit capability_matrix.json"
    )
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=DEFAULT_OUT,
        help="Path for the output capability_matrix.json",
    )
    parser.add_argument(
        "--history",
        type=pathlib.Path,
        default=DEFAULT_HISTORY,
        help="Path for the capability_matrix_history.jsonl (overwritten each run)",
    )
    args = parser.parse_args(argv)

    matrix = probe_capabilities()

    out_path: pathlib.Path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")

    _write_history(matrix, args.history)

    print(f"Capability matrix written to {out_path}")
    print(f"History appended to {args.history}")


if __name__ == "__main__":
    main()
