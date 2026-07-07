"""Boundary tests: empty/zero/minimum input returns a well-defined result.

Feature 4a9a1f61 — symbol-in-binary AC kind.
"""

from __future__ import annotations

from bob.ac_kinds import symbol_in_binary as sib


def test_parse_non_matching_returns_none():
    # An AC of a different kind is not this kind → None, not an exception.
    assert sib.parse_symbol_ac("File exists: src/bob/x.py") is None


def test_parse_bare_prefix_no_body_returns_none():
    # Prefix present but no artifact::symbol body → None (well-defined).
    assert sib.parse_symbol_ac("symbol defined in binary:") is None
    assert sib.parse_symbol_ac("symbol defined in binary:   ") is None


def test_parse_missing_separator_returns_none():
    # No '::' separator → cannot form (artifact, symbol) → None.
    assert sib.parse_symbol_ac("symbol defined in binary: librccl.so") is None


def test_check_non_matching_ac_returns_failed_result():
    # Passing an AC that is not this kind must return a well-defined result
    # (passed False) rather than raising.
    result = sib.check_symbol_defined_in_binary("Function defined: bob.x.y")
    assert result.passed is False
    assert isinstance(result.reason, str) and result.reason


def test_check_missing_artifact_is_well_defined():
    result = sib.check_symbol_defined_in_binary(
        "symbol defined in binary: /no/such/artifact.so::sym"
    )
    assert result.passed is False
    assert isinstance(result.reason, str) and result.reason
    # Fields are all present and typed even in the boundary path.
    assert isinstance(result.command, str)
    assert isinstance(result.evidence, str)
