"""deterministic_output: criterion type for enhanced_verification.

This module provides the ``deterministic_output:`` acceptance-criterion type,
which asserts identical stdout output across runs with seeds 0-3.

It wraps the build-twice infrastructure from Round 2 (F-R2-G07) into a
declarative spec-level criterion.

Criterion syntax
----------------
All fields are optional except ``command``::

    deterministic_output: command="python infer.py"
    deterministic_output: command="python infer.py", seeds=[0,1,2,3]
    deterministic_output: command="python infer.py --seed {seed}"
    deterministic_output: command="python infer.py", env_var=SEED
    deterministic_output: command="python infer.py", timeout=30

The seed is injected in two ways simultaneously:

* As the environment variable named *env_var* (default ``"SEED"``).
* By replacing the literal ``{seed}`` placeholder in the command string.

The criterion passes when all invocations produce identical stdout.

Parameters
----------
command
    Shell command to execute (required).
seeds
    List of integer seeds to test (default: ``[0, 1, 2, 3]``).
env_var
    Environment variable name for seed injection (default: ``"SEED"``).
timeout
    Max seconds to wait for each invocation (default: 60).

Public API
----------
:func:`check_deterministic_output`
    Core checker; returns ``(passed, details)``.

:func:`parse_deterministic_output_args`
    Parse the criterion expression into a ``dict`` of keyword arguments.
"""

from __future__ import annotations

from bob3.enhanced_verification import (
    _parse_deterministic_output_args as parse_deterministic_output_args,
    check_deterministic_output,
)

__all__ = [
    "check_deterministic_output",
    "parse_deterministic_output_args",
]
