"""Boundary tests for capability probing (feature b0a8f699).

Empty, zero, or minimum input must return a well-defined result rather than raising.
"""
from __future__ import annotations

from bob.capability_probe import (
    parse_capability_claim,
    probe_vendor_capability,
    reclassify_infeasible_passthrough,
)


def test_empty_string_parse_returns_none():
    assert parse_capability_claim("") is None


def test_whitespace_parse_returns_none():
    assert parse_capability_claim("   ") is None


def test_empty_string_probe_returns_present_none():
    result = probe_vendor_capability("")
    assert result["present"] is True
    assert result["library"] is None
    assert result["method"] == "none"


def test_minimal_dict_claim_probes():
    result = probe_vendor_capability({"library": "os"})
    assert result["present"] is True
    assert result["symbol"] is None


def test_reclassify_minimal_feature_present():
    out = reclassify_infeasible_passthrough({}, {"present": True})
    assert out["classification"] == "ready"
    assert "capability_evidence" in out


def test_reclassify_minimal_feature_absent():
    out = reclassify_infeasible_passthrough({}, {"present": False})
    assert out["classification"] == "hand-built"
    assert "capability_note" in out
