"""F-R7-478: Ensure no direct `claude --` subprocess calls exist outside spawn_retry.py.

This test is an AST/regex guard: it scans all Python source files under src/
and asserts that no file (except spawn_retry.py itself) contains a direct
`claude --` subprocess invocation.
"""

import ast
import re
from pathlib import Path

_SRC_ROOT = Path(__file__).parents[1] / "src"
_SPAWN_RETRY_FILE = Path(__file__).parents[1] / "src" / "bob" / "orchestrator" / "spawn_retry.py"

# Pattern that identifies a direct `claude --` invocation in source text.
_DIRECT_CLAUDE_PATTERN = re.compile(r'["\']claude\s+--')
# subprocess.run / Popen with "claude" as a list element
_SUBPROCESS_CLAUDE_LIST = re.compile(r'"claude"')


def _is_exempt(path: Path) -> bool:
    """spawn_retry.py is allowed to contain `claude --version` for health probe."""
    return path.resolve() == _SPAWN_RETRY_FILE.resolve()


def _scan_file_for_direct_invocations(path: Path) -> list[tuple[int, str]]:
    """Return list of (line_number, line) for suspicious direct claude invocations."""
    violations = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return violations

    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        # Skip comments
        if stripped.startswith("#"):
            continue
        if _DIRECT_CLAUDE_PATTERN.search(line):
            violations.append((lineno, line.rstrip()))
    return violations


def test_no_direct_claude_invocation_in_src():
    """Assert no Python source file (except spawn_retry.py) contains a direct
    `claude --` subprocess call."""
    violations: dict[str, list[tuple[int, str]]] = {}

    for py_file in sorted(_SRC_ROOT.rglob("*.py")):
        if _is_exempt(py_file):
            continue
        found = _scan_file_for_direct_invocations(py_file)
        if found:
            violations[str(py_file)] = found

    if violations:
        msg_lines = ["Direct `claude --` invocations found outside spawn_retry.py:"]
        for fpath, lines in violations.items():
            for lineno, text in lines:
                msg_lines.append(f"  {fpath}:{lineno}: {text}")
        raise AssertionError("\n".join(msg_lines))


def test_spawn_retry_module_exists():
    """spawn_retry.py must exist as the central routing point."""
    assert _SPAWN_RETRY_FILE.exists(), (
        f"Expected spawn_retry.py at {_SPAWN_RETRY_FILE} — it is the required routing point "
        "for all Claude sub-agent spawns."
    )
