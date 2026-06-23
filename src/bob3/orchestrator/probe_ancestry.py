"""Process ancestry and shell-wrapper predicates for the liveness probe.

Exports two public functions used by is_orchestrator_alive to exclude
false-positive matches:

    collect_ancestor_pids(own_pid) -> frozenset[int]
        Walk /proc PPid chain; returns the full ancestry set including own_pid.

    is_shell_wrapper(cmdline) -> bool
        Returns True when argv[0] is a shell or timeout binary — processes
        that may QUOTE a bobN-run command without themselves being orchestrators.

F-R7-580: the monolithic is_orchestrator_alive previously inlined these
exclusions, making them untestable without mocking os.listdir. This module
exposes them as independently testable predicates against synthetic /proc data.
"""

from __future__ import annotations

import os

_SHELL_BASENAMES: frozenset[str] = frozenset({"bash", "sh", "dash", "zsh", "ksh", "fish"})


def collect_ancestor_pids(own_pid: int) -> frozenset[int]:
    """Walk /proc/<pid>/status PPid chain and return the full ancestry set.

    Starts at own_pid and follows PPid links until PPid <= 1 or a cycle is
    detected. Never raises; returns {own_pid} at minimum if /proc is unreadable.
    """
    visited: set[int] = {own_pid}
    cur = own_pid
    while cur > 1:
        try:
            with open(f"/proc/{cur}/status") as fh:
                ppid = _parse_ppid(fh)
        except OSError:
            break
        if ppid is None or ppid <= 1 or ppid in visited:
            break
        visited.add(ppid)
        cur = ppid
    return frozenset(visited)


def _parse_ppid(fh) -> int | None:
    """Extract PPid value from an open /proc/<pid>/status file handle."""
    for line in fh:
        if line.startswith("PPid:"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return int(parts[1])
                except ValueError:
                    return None
    return None


def is_self_or_ancestor(pid: int) -> bool:
    """Return True when pid is the current process or one of its ancestors.

    Builds the full ancestry set starting from os.getpid() and checks
    membership. This is the documented predicate that is_orchestrator_alive
    delegates to for excluding inherited-shell PIDs.

    Never raises; returns False when /proc is unreadable (conservative: the
    caller should NOT skip the candidate on uncertainty).
    """
    own_pid = os.getpid()
    ancestry = collect_ancestor_pids(own_pid)
    return pid in ancestry


def is_shell_wrapper(cmdline: str) -> bool:
    """Return True when cmdline's argv[0] is a shell or timeout binary.

    Shell binaries checked: bash, sh, dash, zsh, ksh, fish (by basename).
    Also returns True when argv[0] or its basename starts with 'timeout'.

    Shells and timeout wrappers may quote a 'bobN run' command as a string
    argument without themselves being a running orchestrator.

    Returns False for empty cmdline or non-shell argv[0].
    """
    if not cmdline or not cmdline.strip():
        return False
    first = cmdline.split(None, 1)[0]
    first_base = os.path.basename(first)
    if first_base in _SHELL_BASENAMES:
        return True
    if first_base.startswith("timeout"):
        return True
    return False
