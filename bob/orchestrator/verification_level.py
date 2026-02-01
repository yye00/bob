"""
Verification Level — Classification for contract hierarchy.
=============================================================

Every verification contract has a level that determines its role
in the testing hierarchy:

  - UNIT:        Tests a single atomic task in isolation
  - INTEGRATION: Tests that multiple tasks work together (parent-level)
  - SYSTEM:      Tests end-to-end behavior (root-level)

When a task is decomposed into sub-tasks:
  1. Parent's existing contracts are promoted to INTEGRATION
  2. Each child gets new UNIT-level contracts
  3. Root tasks may have SYSTEM-level contracts

After all children complete, the parent's integration contracts
are run to verify the children work together correctly.
"""

from __future__ import annotations

from enum import Enum


class VerificationLevel(str, Enum):
    """Verification rigor level for contracts."""

    UNIT = "unit"                # Single atomic task
    INTEGRATION = "integration"  # Multiple tasks working together
    SYSTEM = "system"            # End-to-end behavior

    @classmethod
    def infer_from_depth(cls, depth: int, is_root: bool = False) -> "VerificationLevel":
        """Infer verification level from task depth in the tree.

        Args:
            depth: Task depth (0 = root)
            is_root: Whether this is a top-level task with no parent

        Returns:
            Appropriate verification level
        """
        if is_root and depth == 0:
            return cls.SYSTEM
        elif depth == 0:
            return cls.INTEGRATION
        else:
            return cls.UNIT
