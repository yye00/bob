"""AST audit for # SCAFFOLDING(...) tags on compensatory code patterns.

Compensatory patterns are defensive workarounds that hide bugs or mask
errors rather than fixing them. Each such pattern in *newly added* diff
lines must carry a ``# SCAFFOLDING(<reason>)`` comment on the same line
or on the immediately preceding added line. Patterns without such a tag
are violations.

Detected compensatory patterns:
- ``pass`` inside an ``except`` block
- ``return <value>`` inside an ``except`` block that does not re-raise
- Any ``except`` body that swallows the error (no ``raise``)
- ``if not <expr>: return`` guard on a single-statement body

Usage::

    from bob.scaffolding_audit import audit_diff, ScaffoldingViolation

    violations = audit_diff(unified_diff_text)
    for v in violations:
        print(f"Line {v.line}: {v.reason}")
        print(f"  Code: {v.code}")
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from bob.cpp_stub_detector import (
    CppStubFinding,
    detect_cpp_stubs,
    find_undefined_symbols,
)


_SCAFFOLDING_RE = re.compile(r"#\s*SCAFFOLDING\(")

_DIFF_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_FILE_HEADER = re.compile(r"^\+\+\+ b/(.+)$")


@dataclass
class ScaffoldingViolation:
    """A compensatory code pattern missing a # SCAFFOLDING(...) tag."""

    line: int
    reason: str
    code: str


# ---------------------------------------------------------------------------
# Diff parsing
# ---------------------------------------------------------------------------

def _parse_diff(diff: str) -> list[tuple[str, list[tuple[int, str]]]]:
    """Parse a unified diff into a list of (filename, [(lineno, text), ...]).

    Only returns added lines (those starting with ``+``), excluding the
    ``+++`` file header lines. Each line number is the line number in the
    *new* file.

    Returns a list of (filename, added_lines) tuples — one per file.
    Files that are not Python (.py) are omitted.
    """
    result: list[tuple[str, list[tuple[int, str]]]] = []
    current_file: str | None = None
    added_lines: list[tuple[int, str]] = []
    current_new_lineno: int = 0

    for raw_line in diff.splitlines():
        # New file in diff
        file_match = _FILE_HEADER.match(raw_line)
        if file_match:
            if current_file is not None and current_file.endswith(".py"):
                result.append((current_file, added_lines))
            current_file = file_match.group(1)
            added_lines = []
            current_new_lineno = 0
            continue

        # Hunk header — update the new-file line counter
        hunk_match = _DIFF_HUNK_HEADER.match(raw_line)
        if hunk_match:
            current_new_lineno = int(hunk_match.group(1))
            continue

        if current_file is None:
            continue

        if raw_line.startswith("+++") or raw_line.startswith("---"):
            continue

        if raw_line.startswith("+"):
            # Added line
            text = raw_line[1:]  # strip the leading '+'
            added_lines.append((current_new_lineno, text))
            current_new_lineno += 1
        elif raw_line.startswith("-"):
            # Removed line — does not advance new-file counter
            pass
        else:
            # Context line
            current_new_lineno += 1

    if current_file is not None and current_file.endswith(".py"):
        result.append((current_file, added_lines))

    return result


# ---------------------------------------------------------------------------
# AST-based pattern detection on the reconstructed new-file source
# ---------------------------------------------------------------------------

def _has_scaffolding_tag(line_text: str) -> bool:
    """Return True if ``line_text`` contains a valid # SCAFFOLDING(...) tag."""
    return bool(_SCAFFOLDING_RE.search(line_text))


def _find_violations_in_added_lines(
    added_lines: list[tuple[int, str]],
) -> list[ScaffoldingViolation]:
    """Detect compensatory patterns in a list of (lineno, text) added lines.

    Strategy:
    1. Reconstruct the fragment of newly added source from the added lines.
    2. Parse it with ``ast``.
    3. Walk the AST for compensatory patterns.
    4. For each hit, check whether the corresponding source line (or the
       immediately preceding added line) carries a SCAFFOLDING tag.
    5. Violations are patterns without a tag.
    """
    if not added_lines:
        return []

    # Build a mapping from internal (1-based) line number within the
    # reconstructed fragment to the real diff line number and text.
    fragment_lines: list[str] = [text for _, text in added_lines]
    lineno_map: dict[int, tuple[int, str]] = {}
    for fragment_idx, (real_lineno, text) in enumerate(added_lines):
        lineno_map[fragment_idx + 1] = (real_lineno, text)

    source = "\n".join(fragment_lines)

    try:
        tree = ast.parse(source, filename="<diff>")
    except SyntaxError:
        return []

    violations: list[ScaffoldingViolation] = []

    def _line_text(fragment_lineno: int) -> str:
        entry = lineno_map.get(fragment_lineno)
        return entry[1] if entry else ""

    def _prev_line_text(fragment_lineno: int) -> str:
        entry = lineno_map.get(fragment_lineno - 1)
        return entry[1] if entry else ""

    def _real_lineno(fragment_lineno: int) -> int:
        entry = lineno_map.get(fragment_lineno)
        return entry[0] if entry else fragment_lineno

    def _is_tagged(fragment_lineno: int) -> bool:
        """Check same-line or preceding-line SCAFFOLDING tag."""
        return (
            _has_scaffolding_tag(_line_text(fragment_lineno))
            or _has_scaffolding_tag(_prev_line_text(fragment_lineno))
        )

    def _add_violation(fragment_lineno: int, reason: str, code: str) -> None:
        if not _is_tagged(fragment_lineno):
            violations.append(
                ScaffoldingViolation(
                    line=_real_lineno(fragment_lineno),
                    reason=reason,
                    code=code.strip(),
                )
            )

    # Walk for Try nodes
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue

        for handler in node.handlers:
            handler_body = handler.body
            if not handler_body:
                continue

            handler_lineno = handler.lineno

            # Determine if the handler re-raises (has a bare ``raise`` or
            # ``raise <expr>``)
            handler_reraises = any(
                isinstance(stmt, ast.Raise) for stmt in ast.walk(handler)
                if stmt is not handler  # don't count the handler itself
            )

            # Pattern: pass inside except
            if (
                len(handler_body) == 1
                and isinstance(handler_body[0], ast.Pass)
            ):
                pass_lineno = handler_body[0].lineno
                _add_violation(
                    pass_lineno,
                    "pass inside except without SCAFFOLDING tag (swallows error)",
                    _line_text(pass_lineno),
                )
                continue

            # Pattern: return inside except (non-re-raise)
            if (
                len(handler_body) == 1
                and isinstance(handler_body[0], ast.Return)
            ):
                return_lineno = handler_body[0].lineno
                _add_violation(
                    return_lineno,
                    "return inside except without re-raise or SCAFFOLDING tag",
                    _line_text(return_lineno),
                )
                continue

            # Pattern: swallowing except (no re-raise, no pass, no return —
            # e.g. just logging or assigning a default)
            if not handler_reraises:
                # The violation is attributed to the first statement in the body
                first_stmt = handler_body[0]
                _add_violation(
                    first_stmt.lineno,
                    "except block swallows error without SCAFFOLDING tag",
                    _line_text(first_stmt.lineno),
                )

    # Walk for if-not-<x>: return guard pattern
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue

        # Must be a negated test: ``if not <expr>:``
        test = node.test
        if not isinstance(test, ast.UnaryOp):
            continue
        if not isinstance(test.op, ast.Not):
            continue

        # Body must be exactly one statement and that statement must be return
        body = node.body
        if len(body) != 1:
            continue
        if not isinstance(body[0], ast.Return):
            continue

        # orelse must be empty (no else/elif branch)
        if node.orelse:
            continue

        if_lineno = node.lineno
        _add_violation(
            if_lineno,
            "if not <x>: return guard without SCAFFOLDING tag",
            _line_text(if_lineno),
        )

    return violations


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def audit_diff(diff: str) -> list[ScaffoldingViolation]:
    """Audit a unified diff for compensatory patterns missing SCAFFOLDING tags.

    Scans only the newly added lines (``+`` lines) in the diff. For each
    Python file in the diff, reconstructs the added source fragment, parses
    it with ``ast``, and checks for compensatory patterns:

    - ``pass`` inside an ``except`` block
    - ``return <value>`` inside an ``except`` block that does not re-raise
    - Any ``except`` body that swallows the error (no ``raise``)
    - ``if not <expr>: return`` single-statement guard

    Each pattern must be accompanied by a ``# SCAFFOLDING(<reason>)``
    comment on the same line or the immediately preceding added line.
    Patterns without such a tag are reported as violations.

    Args:
        diff: A unified diff string (as produced by ``git diff``).

    Returns:
        A list of :class:`ScaffoldingViolation` instances, one per
        untagged compensatory pattern found in the added lines.
    """
    if not diff or not diff.strip():
        return []

    all_violations: list[ScaffoldingViolation] = []

    for _filename, added_lines in _parse_diff(diff):
        violations = _find_violations_in_added_lines(added_lines)
        all_violations.extend(violations)

    return all_violations


def audit_cpp_stubs(
    sources: dict[str, str],
    artifacts: list[str] | None = None,
) -> list[ScaffoldingViolation]:
    """Audit C++/HIP sources (and built artifacts) for stub patterns.

    Bridges the C++/HIP no-stubs gate (:mod:`bob.cpp_stub_detector`) into the
    same :class:`ScaffoldingViolation` shape the Python scaffolding audit emits,
    so both feed the same demote-to-NEEDS_HUMAN path. Covers native sources the
    Python-only gate skipped (``Stub detection skipped (non-Python project)``).

    Args:
        sources: Mapping of native ``filepath -> content``.
        artifacts: Optional list of produced object/library paths to scan for
            link-level undefined symbols.

    Returns:
        A list of :class:`ScaffoldingViolation`, one per stub pattern or
        undefined symbol found.
    """
    violations: list[ScaffoldingViolation] = []

    finding: CppStubFinding
    for finding in detect_cpp_stubs(sources):
        violations.append(
            ScaffoldingViolation(
                line=finding.line,
                reason=f"C++ stub in {finding.filepath}: {finding.reason}",
                code=finding.code,
            )
        )

    if artifacts:
        for undef in find_undefined_symbols(artifacts):
            violations.append(
                ScaffoldingViolation(
                    line=0,
                    reason=(
                        f"undefined symbol {undef.symbol} in {undef.artifact} "
                        "(missing definition — will not link)"
                    ),
                    code=undef.symbol,
                )
            )

    return violations
