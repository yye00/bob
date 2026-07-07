"""Tests for spec-frozen audit exemption enforcement (feature 47b70bd7).

The most dangerous defect of a prior generation: a sub-agent DEFEATED the
universal GPU-execution audit by writing its OWN exemption allowlist (a
``_HOST_OPS`` set) so ops ran on the CPU while the audit went GREEN.

This module enforces the fix:

  1. The set of dispatch-exempt ops is FROZEN in the spec and injected as
     read-only data — implementer code MUST NOT add members to it.
  2. The ONLY structural exemption is a size-0 result.
  3. WHEN an op is classified exempt by any source other than the frozen
     spec-defined set THEN the audit FAILS with
     "exemption not authorized by spec".
"""

from __future__ import annotations

import pytest

from hippy.audit_exemptions import (
    ExemptionError,
    classify_op_exemption,
    get_frozen_exempt_ops,
)


class TestGetFrozenExemptOps:
    def test_returns_frozenset(self) -> None:
        ops = get_frozen_exempt_ops()
        assert isinstance(ops, frozenset)

    def test_empty_by_default_no_op_exempt_by_name(self) -> None:
        # The whole-of-surface clause "EVERY numeric op executes on the device"
        # means no compute op is exempt by name; only size-0 results are.
        assert get_frozen_exempt_ops() == frozenset()

    def test_result_is_immutable(self) -> None:
        ops = get_frozen_exempt_ops()
        with pytest.raises(AttributeError):
            ops.add("sci.sparse.spmv")  # frozenset has no .add

    def test_caller_cannot_mutate_backing_store(self) -> None:
        # Mutating the returned object must not affect a second call — the
        # implementer's code MUST NOT be able to add members to the frozen set.
        ops1 = get_frozen_exempt_ops()
        try:
            ops1 | {"sci.linalg.solve"}  # produces a new set, does not mutate
        except Exception:
            pass
        ops2 = get_frozen_exempt_ops()
        assert ops2 == frozenset()
        assert "sci.linalg.solve" not in ops2


class TestClassifyOpExemptionStructural:
    def test_size_zero_result_is_the_only_structural_exemption(self) -> None:
        verdict = classify_op_exemption("sci.sparse.spmv", result_size=0)
        assert verdict.exempt is True
        assert verdict.authorized is True
        assert "size-0" in verdict.reason or "empty" in verdict.reason.lower()

    def test_nonzero_result_not_exempt_must_dispatch(self) -> None:
        verdict = classify_op_exemption("sci.sparse.spmv", result_size=1024)
        assert verdict.exempt is False
        assert verdict.authorized is False


class TestClassifyOpExemptionSpecFrozen:
    def test_op_in_frozen_set_is_authorized(self) -> None:
        # Inject a frozen set that DOES contain the op — this simulates a spec
        # that authorized it. Authorization must come from the injected set.
        frozen = frozenset({"sci.special.gamma"})
        verdict = classify_op_exemption(
            "sci.special.gamma", result_size=8, frozen_exempt_ops=frozen
        )
        assert verdict.exempt is True
        assert verdict.authorized is True
        assert "spec" in verdict.reason.lower()

    def test_op_not_in_frozen_set_not_exempt(self) -> None:
        frozen = frozenset({"sci.special.gamma"})
        verdict = classify_op_exemption(
            "sci.sparse.spmv", result_size=8, frozen_exempt_ops=frozen
        )
        assert verdict.exempt is False
        assert verdict.authorized is False


class TestClassifyOpExemptionSelfExemptCheat:
    """The oracle-not-gameable cases: an op that tries to exempt ITSELF."""

    def test_docstring_claim_is_not_authorization(self) -> None:
        # An op cannot exempt itself by claiming "host-scalar algorithm intended"
        # in its own docstring. A whole-of-surface clause overrides docstrings.
        verdict = classify_op_exemption(
            "sci.linalg.solve",
            result_size=64,
            claimed_exempt=True,
            claim_source="module docstring: host-scalar algorithm intended",
        )
        assert verdict.exempt is False
        assert verdict.authorized is False
        assert verdict.audit_fails is True
        assert "not authorized by spec" in verdict.reason

    def test_implementer_allowlist_is_not_authorization(self) -> None:
        # The exact cheat: op adds itself to an exemption allowlist supplied by
        # the implementer's own code (not the frozen spec set).
        verdict = classify_op_exemption(
            "sci.sparse.spmv",
            result_size=64,
            claimed_exempt=True,
            claim_source="_HOST_OPS allowlist in audit test",
        )
        assert verdict.exempt is False
        assert verdict.audit_fails is True
        assert "not authorized by spec" in verdict.reason

    def test_claimed_exempt_but_in_frozen_set_is_allowed(self) -> None:
        # If the claim happens to coincide with a genuinely-frozen op, it is
        # authorized BECAUSE the frozen set says so, not because of the claim.
        frozen = frozenset({"sci.special.gamma"})
        verdict = classify_op_exemption(
            "sci.special.gamma",
            result_size=8,
            claimed_exempt=True,
            claim_source="module docstring",
            frozen_exempt_ops=frozen,
        )
        assert verdict.exempt is True
        assert verdict.authorized is True
        assert verdict.audit_fails is False


class TestExemptionErrorType:
    def test_exemption_error_is_valueerror(self) -> None:
        assert issubclass(ExemptionError, ValueError)
