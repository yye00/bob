"""Tests for bob.capability_probe (feature b0a8f699).

The extractor MUST verify vendor/library capability claims against the real
environment before emitting passthrough ACs, and re-classify infeasible ones.
"""
from __future__ import annotations

import pytest

from bob.capability_probe import (
    parse_capability_claim,
    probe_vendor_capability,
    reclassify_infeasible_passthrough,
)


def test_parse_via_pattern():
    claim = parse_capability_claim("DCT via hipfft")
    assert claim == {"library": "hipfft", "symbol": None}


def test_parse_backed_by_pattern():
    claim = parse_capability_claim("eigensolver backed by hipsolver")
    assert claim == {"library": "hipsolver", "symbol": None}


def test_parse_passthrough_with_symbol():
    claim = parse_capability_claim("passthrough to hipfft.dct")
    assert claim == {"library": "hipfft", "symbol": "dct"}


def test_parse_no_claim_returns_none():
    assert parse_capability_claim("a pure-python quicksort implementation") is None


def test_probe_present_module_no_symbol():
    # os is always importable
    result = probe_vendor_capability("helper via os")
    assert result["present"] is True
    assert result["library"] == "os"


def test_probe_present_symbol():
    result = probe_vendor_capability({"library": "os", "symbol": "getcwd"})
    assert result["present"] is True
    assert result["method"] == "attribute"
    assert "found" in result["evidence"]


def test_probe_absent_symbol_records_evidence():
    result = probe_vendor_capability({"library": "os", "symbol": "no_such_attr_xyz"})
    assert result["present"] is False
    assert result["method"] == "attribute"
    assert "ABSENT" in result["evidence"]


def test_probe_missing_module():
    result = probe_vendor_capability("DCT via hipfft_definitely_absent_mod")
    assert result["present"] is False
    assert result["method"] == "import"
    assert "not importable" in result["evidence"]


def test_probe_no_vendor_provider_passes():
    result = probe_vendor_capability("hand-rolled bubble sort in pure python")
    assert result["present"] is True
    assert result["library"] is None
    assert result["method"] == "none"


def test_reclassify_present_stays_ready():
    feat = {"id": "f1", "description": "getcwd via os"}
    probe = probe_vendor_capability({"library": "os", "symbol": "getcwd"})
    out = reclassify_infeasible_passthrough(feat, probe)
    assert out["classification"] == "ready"
    assert out["capability_evidence"]
    # original not mutated
    assert "classification" not in feat


def test_reclassify_absent_becomes_hand_built():
    feat = {"id": "f2", "description": "DCT via hipfft"}
    probe = probe_vendor_capability({"library": "hipfft", "symbol": "dct"})
    # hipfft absent on this machine -> import failure
    out = reclassify_infeasible_passthrough(feat, probe)
    assert out["classification"] == "hand-built"
    assert "hand-built" in out["capability_note"]
    assert out["capability_evidence"]


def test_reclassify_absent_symbol_note_names_target():
    feat = {"id": "f3"}
    probe = {
        "library": "os",
        "symbol": "no_such_attr",
        "present": False,
        "method": "attribute",
        "evidence": "os.no_such_attr ABSENT",
    }
    out = reclassify_infeasible_passthrough(feat, probe)
    assert out["classification"] == "hand-built"
    assert "os.no_such_attr" in out["capability_note"]
