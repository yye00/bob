"""Tests for parity-test anti-cheat AC synthesis (feature 8ff7325a).

A parity/equivalence-style acceptance criterion checks an implementation's
output against a reference. A single frozen expected value is gameable three
ways (return the constant, host-compute-and-disguise, special-case the input).
The fix: when intent is output-equals-reference, synthesized ACs MUST use
randomized-seed inputs and, where an execution substrate is observable, assert
that the real work path actually ran.
"""

from __future__ import annotations

import pytest

from bob.spec_quality.parity_test_anti_cheat import (
    synthesize_parity_ac,
    is_parity_intent,
    has_execution_substrate,
    ensure_randomized_parity_coverage,
)


class TestIsParityIntent:
    def test_output_equals_reference_is_parity(self):
        assert is_parity_intent(
            "the kernel's output must equal the numpy reference value"
        ) is True

    def test_parity_keyword(self):
        assert is_parity_intent("verify parity with scipy") is True

    def test_matches_reference(self):
        assert is_parity_intent("result matches the reference implementation") is True

    def test_non_parity_intent(self):
        assert is_parity_intent("the server returns a 200 status code") is False

    def test_empty_is_not_parity(self):
        assert is_parity_intent("") is False


class TestHasExecutionSubstrate:
    def test_kernel_launch_is_substrate(self):
        assert has_execution_substrate(
            "count the GPU kernel launches"
        ) is True

    def test_subprocess_is_substrate(self):
        assert has_execution_substrate("shells out to a subprocess") is True

    def test_pure_numeric_no_substrate(self):
        assert has_execution_substrate("add two floats") is False


class TestSynthesizeParityAc:
    def test_parity_intent_yields_randomized_ac(self):
        acs = synthesize_parity_ac(
            "the op output must equal the numpy reference over the input"
        )
        assert isinstance(acs, list)
        assert len(acs) >= 1
        joined = " ".join(acs).lower()
        assert "random" in joined
        assert "seed" in joined
        # recognized AC shape: property: or behavior:
        assert any(
            a.strip().lower().startswith(("property:", "behavior:")) for a in acs
        )

    def test_randomized_ac_forbids_frozen_single_value(self):
        acs = synthesize_parity_ac(
            "output equals the reference value for the given input"
        )
        joined = " ".join(acs).lower()
        # expected values precomputed at generation time and replayed
        assert "reference" in joined
        assert "seed" in joined

    def test_execution_substrate_adds_evidence_check(self):
        acs = synthesize_parity_ac(
            "the CUDA kernel output must match the numpy reference; "
            "count kernel launches"
        )
        joined = " ".join(acs).lower()
        assert "execution evidence" in joined or "evidence" in joined

    def test_no_substrate_omits_evidence(self):
        acs = synthesize_parity_ac(
            "the pure-python transform output equals the reference value"
        )
        joined = " ".join(acs).lower()
        assert "execution evidence" not in joined

    def test_non_parity_intent_returns_empty(self):
        acs = synthesize_parity_ac("the CLI prints a help banner")
        assert acs == []

    def test_num_seeds_reflected_in_ac(self):
        acs = synthesize_parity_ac(
            "output equals reference", num_seeds=64
        )
        joined = " ".join(acs)
        assert "64" in joined

    def test_explicit_substrate_override_true(self):
        acs = synthesize_parity_ac(
            "output equals reference", execution_substrate=True
        )
        joined = " ".join(acs).lower()
        assert "evidence" in joined

    def test_explicit_substrate_override_false(self):
        acs = synthesize_parity_ac(
            "the CUDA kernel output matches reference",
            execution_substrate=False,
        )
        joined = " ".join(acs).lower()
        assert "execution evidence" not in joined


class TestEnsureRandomizedParityCoverage:
    def test_frozen_ac_gets_randomized_companion(self):
        criteria = [
            "File exists: src/op.py",
            "pytest: tests/test_op.py — output equals the reference value 42",
        ]
        out = ensure_randomized_parity_coverage(
            criteria,
            intent="op output equals the numpy reference",
        )
        # original structural ACs preserved (never weakened)
        assert "File exists: src/op.py" in out
        assert any("output equals the reference value 42" in c for c in out)
        # at least one randomized/property AC added
        assert any(
            c.strip().lower().startswith(("property:", "behavior:")) for c in out
        )
        assert len(out) > len(criteria)

    def test_already_has_randomized_ac_is_idempotent(self):
        criteria = [
            "File exists: src/op.py",
            "property: output matches reference over 32 randomized seeds",
        ]
        out = ensure_randomized_parity_coverage(
            criteria, intent="op output equals reference"
        )
        # no duplicate randomized AC added
        prop_count = sum(
            1 for c in out if "randomized seeds" in c.lower()
        )
        assert prop_count == 1

    def test_non_parity_criteria_unchanged(self):
        criteria = ["File exists: src/x.py", "Function defined: x.f"]
        out = ensure_randomized_parity_coverage(
            criteria, intent="a plain CRUD feature"
        )
        assert out == criteria
