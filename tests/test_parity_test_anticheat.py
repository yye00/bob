"""Tests for the hippy parity-test anti-cheat façade (feature 7951f7fc).

Verifies the AC-named entry points ``synthesize_parity_ac`` and
``requires_execution_evidence`` on ``hippy.parity_test_anticheat``, and that
the hippy façade shares behaviour with the bob synthesis core.
"""

from __future__ import annotations

import pytest

from hippy.parity_test_anticheat import (
    ensure_randomized_parity_coverage,
    has_execution_substrate,
    is_parity_intent,
    requires_execution_evidence,
    synthesize_parity_ac,
)


class TestSynthesizeParityAc:
    def test_parity_intent_yields_randomized_seed_ac(self):
        acs = synthesize_parity_ac(
            "the op output must equal the numpy reference over the input"
        )
        assert isinstance(acs, list)
        assert acs
        joined = " ".join(acs).lower()
        assert "random" in joined
        assert "seed" in joined
        assert "reference" in joined
        assert any(
            a.strip().lower().startswith(("property:", "behavior:")) for a in acs
        )

    def test_non_parity_intent_returns_empty(self):
        assert synthesize_parity_ac("the CLI prints a help banner") == []

    def test_substrate_intent_adds_execution_evidence(self):
        acs = synthesize_parity_ac(
            "the CUDA kernel output must match the numpy reference; "
            "count kernel launches"
        )
        joined = " ".join(acs).lower()
        assert "evidence" in joined

    def test_pure_numeric_omits_execution_evidence(self):
        acs = synthesize_parity_ac(
            "the pure-python transform output equals the reference value"
        )
        joined = " ".join(acs).lower()
        assert "execution evidence" not in joined

    def test_num_seeds_reflected(self):
        acs = synthesize_parity_ac("output equals reference", num_seeds=64)
        assert "64" in " ".join(acs)

    def test_none_intent_raises(self):
        with pytest.raises(ValueError):
            synthesize_parity_ac(None)  # type: ignore[arg-type]


class TestRequiresExecutionEvidence:
    def test_parity_with_substrate_requires_evidence(self):
        assert requires_execution_evidence(
            "the CUDA kernel output must match the numpy reference"
        ) is True

    def test_parity_without_substrate_does_not_require_evidence(self):
        assert requires_execution_evidence(
            "the pure-python transform output equals the reference value"
        ) is False

    def test_non_parity_with_substrate_does_not_require_evidence(self):
        # a substrate alone is not enough — the intent must be parity-shaped.
        assert requires_execution_evidence("launch a CUDA kernel") is False

    def test_non_parity_returns_false(self):
        assert requires_execution_evidence("the CLI prints a help banner") is False

    def test_empty_intent_returns_false(self):
        assert requires_execution_evidence("") is False

    def test_none_intent_raises(self):
        with pytest.raises(ValueError):
            requires_execution_evidence(None)  # type: ignore[arg-type]

    def test_requires_evidence_agrees_with_synthesizer(self):
        intent = "the GPU kernel output must equal the numpy reference"
        acs = synthesize_parity_ac(intent)
        joined = " ".join(acs).lower()
        if requires_execution_evidence(intent):
            assert "evidence" in joined
        else:
            assert "execution evidence" not in joined


class TestFacadeReexports:
    def test_is_parity_intent_reexported(self):
        assert is_parity_intent("output equals the reference") is True
        assert is_parity_intent("plain crud endpoint") is False

    def test_has_execution_substrate_reexported(self):
        assert has_execution_substrate("count kernel launches") is True
        assert has_execution_substrate("add two floats") is False

    def test_ensure_randomized_parity_coverage_reexported(self):
        criteria = [
            "File exists: src/op.py",
            "pytest: tests/test_op.py — output equals the reference value 42",
        ]
        out = ensure_randomized_parity_coverage(
            criteria, intent="op output equals the numpy reference"
        )
        assert "File exists: src/op.py" in out
        assert any(
            c.strip().lower().startswith(("property:", "behavior:")) for c in out
        )
        assert len(out) > len(criteria)
