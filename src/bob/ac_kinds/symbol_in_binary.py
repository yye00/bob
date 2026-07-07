"""symbol-in-binary AC kind — nm/objdump/readelf defined-symbol check.

A source-level ``Function defined:`` check cannot prove a symbol actually made
it into the shipped artifact with a real, linkable body: a header declaration
or a body optimized away can pass a source probe yet be *undefined* in the
library.  This AC kind closes that gap.

Syntax
------
::

    symbol defined in binary: <artifact>::<demangled-or-mangled-symbol>

For example::

    symbol defined in binary: build/librccl.so::ncclAllReduce

Semantics
---------
The named *artifact* (object file or shared library) is inspected with
``nm -C`` (falling back to ``objdump -T`` / ``readelf -s``) and the *symbol*
must appear as a **DEFINED** text/data symbol — nm type ``T``/``t`` (or ``D``/
``d``/``W``/``w``) — and NOT as an ``U`` (undefined / referenced-only) symbol.
The command run and its raw output are persisted on the result as evidence,
complementing the link-level layer of the no-stubs gate.

Public API
----------
parse_symbol_ac(criterion) -> SymbolAC | None
check_symbol_defined_in_binary(criterion) -> SymbolCheckResult
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
from dataclasses import dataclass, field

#: Canonical AC prefix (matched case-insensitively).
_PREFIX = "symbol defined in binary:"

#: nm symbol-type letters that count as *defined* (upper = global, lower = local).
#: T/t = text, D/d = initialized data, B/b = BSS, R/r = read-only data,
#: W/w = weak.  ``U`` (undefined) and ``?`` deliberately excluded.
_DEFINED_TYPES = frozenset("TtDdBbRrWwVvGgSs")


@dataclass(frozen=True)
class SymbolAC:
    """Parsed ``symbol defined in binary:`` acceptance criterion."""

    artifact: str
    symbol: str


@dataclass(frozen=True)
class SymbolCheckResult:
    """Outcome of a binary defined-symbol check (evidence-bearing)."""

    passed: bool
    reason: str
    command: str = ""
    evidence: str = ""
    artifact: str = ""
    symbol: str = ""
    matched_types: tuple[str, ...] = field(default_factory=tuple)


def _validate_str(criterion: object, func: str) -> str:
    if not isinstance(criterion, str):
        raise ValueError(
            f"{func}: criterion must be a str, got {type(criterion).__name__!r}"
        )
    stripped = criterion.strip()
    if not stripped:
        raise ValueError(f"{func}: criterion must be a non-empty string")
    return stripped


def _is_kind(stripped: str) -> bool:
    return stripped.lower().startswith(_PREFIX)


def parse_symbol_ac(criterion: str) -> SymbolAC | None:
    """Parse a ``symbol defined in binary:`` AC into ``SymbolAC``.

    Returns ``None`` when *criterion* is not this AC kind, or when the prefix
    is present but no ``artifact::symbol`` body can be extracted (a well-defined
    "not parseable as this kind" answer).

    :raises ValueError: when *criterion* is not a non-empty string.
    """
    stripped = _validate_str(criterion, "parse_symbol_ac")

    if not _is_kind(stripped):
        return None

    body = stripped[len(_PREFIX):].strip()
    if not body or "::" not in body:
        return None

    # Split on the FIRST '::' so demangled C++ names (ns::Class::method) keep
    # their internal separators as part of the symbol.
    artifact, _, symbol = body.partition("::")
    artifact = artifact.strip()
    symbol = symbol.strip()
    if not artifact or not symbol:
        return None

    return SymbolAC(artifact=artifact, symbol=symbol)


def _run(cmd: list[str]) -> tuple[str, str]:
    """Run *cmd*, returning (command_string, combined_output).

    Never raises on a non-zero exit — tool output (even on failure) is the
    evidence we want to persist.
    """
    cmd_str = " ".join(cmd)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        return cmd_str, f"<error running {cmd_str}: {exc}>"
    return cmd_str, (proc.stdout or "") + (proc.stderr or "")


def _symbol_defined_in_output(output: str, symbol: str, tool: str) -> tuple[bool, tuple[str, ...]]:
    """Return (is_defined, matched_type_letters) for *symbol* in tool *output*.

    ``nm``/``nm -C`` lines look like ``<addr> <type> <name>``; a bare ``U``
    line has no address (``         U name``).  ``objdump -T`` / ``readelf -s``
    use different columns, so for those we fall back to substring presence of
    the symbol on a non-``UND``/``*UND*`` line.
    """
    matched: list[str] = []
    defined = False
    for line in output.splitlines():
        if symbol not in line:
            continue
        parts = line.split()
        if not parts:
            continue
        if tool == "nm":
            # Expect: [addr] <type> <name...>.  Undefined form: "U name".
            if parts[0] == "U":
                continue
            # type is the token immediately before the symbol name.
            type_letter = None
            for i, tok in enumerate(parts):
                if len(tok) == 1 and tok.isalpha() and i + 1 < len(parts):
                    type_letter = tok
            if type_letter and type_letter in _DEFINED_TYPES:
                # Confirm the symbol is a whole-token match, not a substring.
                if symbol in parts:
                    defined = True
                    matched.append(type_letter)
        else:
            # objdump -T / readelf -s: undefined rows carry UND / *UND*.
            upper = line.upper()
            if "UND" in upper:
                continue
            if symbol in parts:
                defined = True
                matched.append(tool)
    return defined, tuple(matched)


def check_symbol_defined_in_binary(criterion: str) -> SymbolCheckResult:
    """Verify that a symbol is a DEFINED symbol in a built artifact.

    Runs ``nm -C`` (then ``objdump -T`` / ``readelf -s`` as fallbacks) on the
    artifact named in *criterion* and returns a :class:`SymbolCheckResult`.
    The command and its raw output are persisted on the result as evidence.

    Returns a ``passed=False`` result — never raises — when the AC is not this
    kind, or when the artifact is missing or the symbol is absent/undefined.

    :raises ValueError: when *criterion* is not a non-empty string, or when it
        matches this AC kind but is malformed (no ``artifact::symbol`` body) —
        a matched-but-invalid AC must fail loudly, not silently pass.
    """
    stripped = _validate_str(criterion, "check_symbol_defined_in_binary")

    if not _is_kind(stripped):
        return SymbolCheckResult(
            passed=False,
            reason=f"not a 'symbol defined in binary:' AC: {stripped!r}",
        )

    parsed = parse_symbol_ac(stripped)
    if parsed is None:
        raise ValueError(
            "check_symbol_defined_in_binary: malformed 'symbol defined in "
            f"binary:' AC, expected '<artifact>::<symbol>' body: {stripped!r}"
        )

    artifact_path = pathlib.Path(parsed.artifact)
    if not artifact_path.exists():
        return SymbolCheckResult(
            passed=False,
            reason=f"artifact not found: {parsed.artifact}",
            artifact=parsed.artifact,
            symbol=parsed.symbol,
        )

    # Try nm -C first, then objdump -T, then readelf -s.
    tools = [
        ("nm", ["nm", "-C", "--defined-only", str(artifact_path)]),
        ("objdump", ["objdump", "-T", str(artifact_path)]),
        ("readelf", ["readelf", "-sW", str(artifact_path)]),
    ]

    last_cmd = ""
    last_output = ""
    for tool, cmd in tools:
        if shutil.which(cmd[0]) is None:
            continue
        # nm --defined-only already filters undefined; fall back without it if
        # the option is unsupported (older binutils).
        cmd_str, output = _run(cmd)
        last_cmd, last_output = cmd_str, output
        # For nm --defined-only, every listed line is defined → presence check.
        if tool == "nm":
            defined, matched = _symbol_defined_in_output(output, parsed.symbol, tool)
            # With --defined-only, a whole-token match means defined.
            if not defined:
                for line in output.splitlines():
                    if parsed.symbol in line.split():
                        defined = True
                        matched = ("defined-only",)
                        break
        else:
            defined, matched = _symbol_defined_in_output(output, parsed.symbol, tool)

        if defined:
            return SymbolCheckResult(
                passed=True,
                reason=(
                    f"symbol {parsed.symbol!r} defined in {parsed.artifact} "
                    f"(via {tool})"
                ),
                command=cmd_str,
                evidence=output,
                artifact=parsed.artifact,
                symbol=parsed.symbol,
                matched_types=matched,
            )

    return SymbolCheckResult(
        passed=False,
        reason=(
            f"symbol {parsed.symbol!r} not found as a DEFINED symbol in "
            f"{parsed.artifact}"
        ),
        command=last_cmd,
        evidence=last_output,
        artifact=parsed.artifact,
        symbol=parsed.symbol,
    )


__all__ = [
    "SymbolAC",
    "SymbolCheckResult",
    "parse_symbol_ac",
    "check_symbol_defined_in_binary",
]
