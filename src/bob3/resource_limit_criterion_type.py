"""resource_limit: criterion type for enhanced_verification.

This module provides the ``resource_limit:`` acceptance-criterion type,
which enforces hard wall-clock and peak-memory caps on a command.

Prevents indefinite-run gaming by spec authors: a command that would run
forever or consume unbounded memory is killed and the criterion fails.
Integrated with the spawn watchdog from Round 2 (F-R2-127).

Criterion syntax
----------------
All fields are optional except ``command``::

    resource_limit: command="python train.py"
    resource_limit: command="python train.py", wall_clock_s=30
    resource_limit: command="python train.py", peak_mem_mb=512
    resource_limit: command="python train.py", wall_clock_s=60, peak_mem_mb=256

Parameters
----------
command
    Shell command to run (required).
wall_clock_s
    Maximum allowed wall-clock seconds.  When the command exceeds this, the
    criterion fails.  ``None`` means no wall-clock cap beyond *timeout*.
peak_mem_mb
    Maximum allowed peak resident-set size in mebibytes.  ``None`` means
    no memory cap.
timeout
    Hard subprocess kill timeout in seconds.  Defaults to *wall_clock_s* + 5s
    of grace, or the global ``BOB3_CRITERION_EXEC_TIMEOUT``.

The criterion PASSES when the command exits 0 within all caps.
The criterion FAILS when:
- ``command`` is missing or empty
- the command times out (``wall_clock_s`` exceeded)
- the command exits with a non-zero code
- peak RSS exceeds ``peak_mem_mb``

Public API
----------
:func:`check_resource_limit`
    Core checker; returns ``(passed, details)``.

:func:`parse_resource_limit_args`
    Parse the criterion expression into a ``dict`` of keyword arguments.
"""

from __future__ import annotations

from bob3.enhanced_verification import (
    _parse_resource_limit_args as parse_resource_limit_args,
    check_resource_limit,
)

__all__ = [
    "check_resource_limit",
    "parse_resource_limit_args",
]
