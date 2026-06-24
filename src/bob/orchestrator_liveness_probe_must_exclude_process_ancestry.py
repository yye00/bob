"""Feature 34ace496: Orchestrator-liveness probe MUST exclude process ancestry AND shell wrappers.

F-R7-567 substring-match on ``bob[0-9]+ run`` tripped when the parent bash's
``eval`` string contained the bobN-run command we were about to launch,
blocking bob version 17 first-boot for 5 minutes until manual probe-patch
was applied.

Root cause (2026-05-31 ~05:15Z):
    ``is_orchestrator_alive`` excluded only ``own_pid``; every ancestor shell
    that quoted the command was treated as a live orchestrator.

Fix: the probe MUST consume two independently testable predicates:

  * ``is_self_or_ancestor(pid)``  — excludes current process and all ancestors
  * ``is_shell_wrapper(cmdline)`` — excludes bash/sh/dash/zsh/ksh/fish and
    ``timeout`` wrappers that quote the bobN-run command as a string argument

Both predicates are exported by ``bob.orchestrator.probe_ancestry`` so they
can be tested against synthetic /proc layouts without ``unittest.mock.patch``
of ``os.listdir``.
"""

from __future__ import annotations

from bob.orchestrator.probe_ancestry import (
    collect_ancestor_pids,
    is_self_or_ancestor,
    is_shell_wrapper,
)
from bob.orchestrator.liveness_probe import is_orchestrator_alive

__all__ = [
    "orchestrator_liveness_probe_must_exclude_process_ancestry",
]


def orchestrator_liveness_probe_must_exclude_process_ancestry() -> bool:
    """Return True if an orchestrator matching 'bob[0-9]+ run' is alive.

    Wraps ``is_orchestrator_alive`` from ``bob.orchestrator.liveness_probe``
    which applies the two mandatory exclusion predicates:

    1. ``is_self_or_ancestor(pid)`` — skips the current process and every PID
       in its ancestry chain (parent, grandparent, …) so that a bash shell
       whose eval-string quotes the bobN-run command we are about to execute
       is never treated as a running orchestrator.

    2. ``is_shell_wrapper(cmdline)`` — skips processes whose argv[0] is a
       shell binary (bash, sh, dash, zsh, ksh, fish) or starts with
       ``timeout``.  These wrappers may hold the bobN-run command in their
       argument string without themselves being a persistent orchestrator
       process.

    Returns False when no such live orchestrator process is found (i.e. safe
    to proceed with launch).  Returns True when a genuine remote orchestrator
    is detected and the launch must be aborted.
    """
    return is_orchestrator_alive()
