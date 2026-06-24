"""behavioral_signature: criterion type for enhanced_verification.

This module provides the ``behavioral_signature:`` acceptance-criterion type,
which validates the shape of a loss curve produced by a command rather than
just checking a final scalar value.

It catches fake training scripts that emit hardcoded or random losses that
don't exhibit genuine learning dynamics.

Criterion syntax
----------------
All fields are optional except ``command``::

    behavioral_signature: command="python train.py"
    behavioral_signature: command="python train.py", monotone_decrease=true
    behavioral_signature: command="python train.py", converges_within=50
    behavioral_signature: command="python train.py", monotone_decrease=true, converges_within=50
    behavioral_signature: command="python train.py", min_steps=5, max_final_loss=0.5
    behavioral_signature: command="python train.py", loss_key=val_loss

The command's stdout/stderr is scanned for lines containing a numeric loss
value. Recognized formats (matched in order):

* ``loss: 0.45``
* ``loss=0.45``
* ``val_loss: 0.45``
* ``{"loss": 0.45}``   (JSON with a ``"loss"`` or configured ``loss_key``)

Parameters
----------
command
    Shell command to run (required).
monotone_decrease
    If true, each loss value must be strictly less than the previous.
converges_within
    The loss must stop changing significantly within N steps.
min_steps
    Minimum number of loss values that must appear.
max_final_loss
    The last reported loss must be at or below this threshold.
loss_key
    Key to extract from JSON output lines (default: ``"loss"``).
timeout
    Max seconds to wait for the command (default: 60).

Public API
----------
:func:`check_behavioral_signature`
    Core checker; returns ``(passed, details)``.

:func:`parse_behavioral_signature_args`
    Parse the criterion expression into a ``dict`` of keyword arguments.
"""

from __future__ import annotations

from bob.enhanced_verification import (
    _parse_behavioral_signature_args as parse_behavioral_signature_args,
    check_behavioral_signature,
)

__all__ = [
    "check_behavioral_signature",
    "parse_behavioral_signature_args",
]
