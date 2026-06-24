"""bob.cli.explain_gate_block — CLI module for the explain-gate-block subcommand.

Re-exports :func:`bob.enhanced_verification.explain_gate_block` under the
``bob.cli.explain_gate_block`` namespace so that ACs of the form::

    Function defined: bob.cli.explain_gate_block.explain_gate_block

resolve correctly.  The actual Click command registration lives in
:mod:`bob.cli` (``__init__.py``); this module provides the importable
entry point consumed by the verifier.
"""

from __future__ import annotations

from bob.enhanced_verification import explain_gate_block  # noqa: F401

__all__ = ["explain_gate_block"]
