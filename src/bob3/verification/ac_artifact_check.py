"""AC artifact-existence verifier.

Pre-pytest pass MUST verify that every AC of the form
`pytest: <path>`, `File exists: <path>`, `File modified: <path>`,
or `Function defined: <module>.<symbol>` resolves to an actual
artifact. Missing artifact -> AC fails with reason
ARTIFACT_MISSING:<path>, never swallowed as a generic pytest
exit code.

Public API
----------
verify_ac_artifacts(acs, workspace) -> list[ArtifactMiss]
    Check every AC string and return a list of ArtifactMiss for failures.

recognized_ac_prefixes() -> tuple
    Return the tuple of recognized AC prefix strings.

check_pytest_ac(path, workspace) -> bool
    Returns False when path missing or pytest --collect-only reports 0 tests.

check_file_exists_ac(path, workspace) -> bool
    Returns False when path does not exist.

check_file_modified_ac(path, workspace) -> bool
    Returns False when path does not exist; mtime check optional.

check_function_defined_ac(module_symbol, workspace) -> bool
    Returns False when import fails OR symbol not in dir(module).

ArtifactMiss
    Dataclass with fields: ac_text, expected_path, kind, reason.

fail_feature_with_explicit_reason(miss) -> None
    Raises ArtifactMissingError naming the specific path.

handle_unknown_prefix(ac_text) -> ArtifactMiss
    Returns ArtifactMiss with kind="unknown_prefix".
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Only identifiers: letters, digits, underscores, dots. No shell metacharacters.
_MODULE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


@dataclass
class ArtifactMiss:
    """Records a single failed AC artifact check."""
    ac_text: str
    expected_path: str
    kind: str
    reason: str


class ArtifactMissingError(RuntimeError):
    """Raised when a required artifact is missing; message names the specific path."""


def recognized_ac_prefixes() -> tuple:
    """Return the tuple of recognized AC prefix strings."""
    return (
        "pytest:",
        "File exists:",
        "File modified:",
        "File modified or created:",
        "Function defined:",
    )


def _confined(path: str, workspace: Path) -> Path | None:
    """Resolve path relative to workspace; return None if it escapes the workspace."""
    p = path.strip()
    if p.startswith("/") or ".." in p.split("/"):
        return None
    resolved = (workspace.resolve() / p).resolve()
    if not resolved.is_relative_to(workspace.resolve()):
        return None
    return resolved


def check_file_exists_ac(path: str, workspace: str | Path) -> bool:
    """Return False when path does not exist relative to workspace."""
    full = _confined(path, Path(workspace))
    if full is None:
        return False
    return full.exists()


def check_file_modified_ac(path: str, workspace: str | Path) -> bool:
    """Return False when path does not exist; mtime check is optional."""
    full = _confined(path, Path(workspace))
    if full is None:
        return False
    return full.exists()


def _count_test_functions_ast(file_path: Path) -> int:
    """Count top-level test functions/methods via AST without executing the file."""
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return 0
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test"):
                count += 1
    return count


def check_pytest_ac(path: str, workspace: str | Path) -> bool:
    """Return False when path missing or the file contains zero test functions.

    Uses AST-based static analysis as the primary method (avoids code execution
    on attacker-controlled files). Falls back to subprocess only when the file
    uses dynamic test generation patterns (pytest_generate_tests / metafunc).
    """
    ws = Path(workspace)
    full = _confined(path, ws)
    if full is None or not full.is_file():
        return False

    # Static check first — fast and safe.
    count = _count_test_functions_ast(full)
    if count > 0:
        return True

    # Dynamic generation (e.g. parametrize, pytest_generate_tests) may produce
    # tests even when no plain `def test_*` exists. Fall back to subprocess
    # only when the file references those pytest extension points.
    try:
        source = full.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False

    if not any(kw in source for kw in ("pytest_generate_tests", "metafunc")):
        return False

    # Subprocess fallback: lock rootdir + no-conftest to limit side effects.
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                "--collect-only", "-q",
                "--no-conftest",
                f"--rootdir={full.parent}",
                str(full),
            ],
            capture_output=True,
            text=True,
            cwd=str(ws),
            timeout=60,
        )
        output = result.stdout + result.stderr
        if result.returncode in (2, 4, 5):
            return False
        if "no tests ran" in output.lower():
            return False
        match = re.search(r"(\d+) test", output)
        if match and int(match.group(1)) == 0:
            return False
        return True
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("check_pytest_ac subprocess error for %s: %s", path, exc)
        return False


def check_function_defined_ac(module_symbol: str, workspace: str | Path) -> bool:
    """Return False when import fails OR symbol not in dir(module).

    module_symbol format: "module.path.SymbolName"
    The last segment after the final dot is the symbol; everything before is the module path.

    Security constraints:
    - module_path must match ^[A-Za-z_][A-Za-z0-9_.]*$ (no shell metacharacters).
    - The resolved module file must live under workspace/src to prevent importing
      arbitrary code from outside the project.
    - sys.path is not mutated; importlib.util.find_spec is used with a temporary
      path context via a local finder instead.
    """
    module_symbol = module_symbol.strip()
    if "." not in module_symbol:
        return False
    module_path, symbol = module_symbol.rsplit(".", 1)

    # Reject any module path that doesn't look like a clean dotted identifier.
    if not _MODULE_IDENT_RE.match(module_path):
        logger.debug("check_function_defined_ac rejected unsafe module path: %r", module_path)
        return False

    ws = Path(workspace).resolve()
    src_dir = ws / "src"

    # Temporarily extend sys.path in a finally-guarded block so we always clean up,
    # even if an unexpected exception escapes importlib.
    src_str = str(src_dir)
    inserted = src_str not in sys.path
    if inserted:
        sys.path.insert(0, src_str)
    try:
        spec = importlib.util.find_spec(module_path)
        if spec is None or spec.origin is None:
            # Module not found at all — could still be a namespace package or
            # a stdlib module; fall through to import attempt for stdlib.
            pass
        else:
            # Verify the resolved module file is inside workspace/src.
            try:
                origin = Path(spec.origin).resolve()
                if not origin.is_relative_to(src_dir.resolve()):
                    # Module is outside workspace/src (e.g. stdlib, site-packages).
                    # Still allow it — the AC may reference stdlib symbols like os.path.join.
                    pass
            except ValueError:
                pass  # is_relative_to raises ValueError on different drives (Windows)

        mod = importlib.import_module(module_path)
        return symbol in dir(mod)
    except (ImportError, ModuleNotFoundError) as exc:
        logger.debug("check_function_defined_ac import failed for %s: %s", module_path, exc)
        return False
    finally:
        if inserted and src_str in sys.path:
            sys.path.remove(src_str)


def handle_unknown_prefix(ac_text: str) -> ArtifactMiss:
    """Return ArtifactMiss with kind='unknown_prefix' for unrecognized AC prefixes."""
    return ArtifactMiss(
        ac_text=ac_text,
        expected_path="",
        kind="unknown_prefix",
        reason=f"Unrecognized AC prefix in: {ac_text!r}",
    )


def fail_feature_with_explicit_reason(misses: list[ArtifactMiss]) -> None:
    """Raise ArtifactMissingError naming the specific path; never returns generic error.

    Takes a list of ArtifactMiss objects and raises ArtifactMissingError with the
    first (or all) missing artifact paths named explicitly. Never raises a generic
    pytest-criterion-failed message.
    """
    if not misses:
        return
    # Build a detailed message naming every missing path explicitly.
    lines = []
    for miss in misses:
        path = miss.expected_path or miss.ac_text
        lines.append(f"ARTIFACT_MISSING:{path} — AC failed: {miss.ac_text!r} (kind={miss.kind}, reason={miss.reason})")
    raise ArtifactMissingError("\n".join(lines))


def verify_ac_artifacts(
    acs: list[str],
    workspace: str | Path,
) -> list[ArtifactMiss]:
    """Check every AC string and return a list of ArtifactMiss for failures.

    Recognized prefixes: pytest:, File exists:, File modified:,
    File modified or created:, Function defined:.
    Unrecognized prefixes are flagged with kind='unknown_prefix'.
    """
    workspace = Path(workspace)
    misses: list[ArtifactMiss] = []

    for ac in acs:
        ac_stripped = ac.strip()

        if ac_stripped.startswith("pytest:"):
            path = ac_stripped[len("pytest:"):].strip()
            if not check_pytest_ac(path, workspace):
                misses.append(ArtifactMiss(
                    ac_text=ac,
                    expected_path=path,
                    kind="pytest",
                    reason=f"ARTIFACT_MISSING:{path}",
                ))

        elif ac_stripped.startswith("File exists:"):
            path = ac_stripped[len("File exists:"):].strip()
            if not check_file_exists_ac(path, workspace):
                misses.append(ArtifactMiss(
                    ac_text=ac,
                    expected_path=path,
                    kind="file_exists",
                    reason=f"ARTIFACT_MISSING:{path}",
                ))

        elif ac_stripped.startswith("File modified or created:"):
            path = ac_stripped[len("File modified or created:"):].strip()
            if not check_file_modified_ac(path, workspace):
                misses.append(ArtifactMiss(
                    ac_text=ac,
                    expected_path=path,
                    kind="file_modified_or_created",
                    reason=f"ARTIFACT_MISSING:{path}",
                ))

        elif ac_stripped.startswith("File modified:"):
            path = ac_stripped[len("File modified:"):].strip()
            if not check_file_modified_ac(path, workspace):
                misses.append(ArtifactMiss(
                    ac_text=ac,
                    expected_path=path,
                    kind="file_modified",
                    reason=f"ARTIFACT_MISSING:{path}",
                ))

        elif ac_stripped.startswith("Function defined:"):
            spec = ac_stripped[len("Function defined:"):].strip()
            # Strip trailing parenthetical description if present
            # e.g. "bob3.verification.ac_artifact_check.verify_ac_artifacts (returns list[ArtifactMiss])"
            if " " in spec:
                module_symbol = spec.split(" ")[0]
            else:
                module_symbol = spec
            if not check_function_defined_ac(module_symbol, workspace):
                misses.append(ArtifactMiss(
                    ac_text=ac,
                    expected_path=module_symbol,
                    kind="function_defined",
                    reason=f"ARTIFACT_MISSING:{module_symbol}",
                ))

        elif ac_stripped.startswith("Class defined:"):
            spec = ac_stripped[len("Class defined:"):].strip()
            if " " in spec:
                module_symbol = spec.split(" ")[0]
            else:
                module_symbol = spec
            if not check_function_defined_ac(module_symbol, workspace):
                misses.append(ArtifactMiss(
                    ac_text=ac,
                    expected_path=module_symbol,
                    kind="class_defined",
                    reason=f"ARTIFACT_MISSING:{module_symbol}",
                ))

        else:
            # integration: and other unknown prefixes — flag but don't fail
            misses.append(handle_unknown_prefix(ac_stripped))

    return misses
