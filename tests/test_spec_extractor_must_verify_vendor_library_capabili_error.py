"""Error-path tests for capability probing (feature b0a8f699).

Invalid input raises ValueError and the function does not silently succeed.
"""
from __future__ import annotations

import pytest

from bob.capability_probe import (
    parse_capability_claim,
    probe_vendor_capability,
    reclassify_infeasible_passthrough,
)


def test_parse_non_string_raises():
    with pytest.raises(ValueError):
        parse_capability_claim(123)


def test_probe_non_str_non_dict_raises():
    with pytest.raises(ValueError):
        probe_vendor_capability(123)


def test_probe_dict_without_library_raises():
    with pytest.raises(ValueError):
        probe_vendor_capability({"symbol": "dct"})


def test_probe_dict_empty_library_raises():
    with pytest.raises(ValueError):
        probe_vendor_capability({"library": ""})


def test_reclassify_non_dict_feature_raises():
    with pytest.raises(ValueError):
        reclassify_infeasible_passthrough("notadict", {"present": True})


def test_reclassify_non_dict_probe_raises():
    with pytest.raises(ValueError):
        reclassify_infeasible_passthrough({}, "notadict")


def test_reclassify_probe_missing_present_raises():
    with pytest.raises(ValueError):
        reclassify_infeasible_passthrough({}, {"library": "os"})
