"""Boundary tests: empty/zero/minimum input returns a well-defined result, not a raise."""

from __future__ import annotations

from bob.toolchain_preflight import (
    ToolchainPins,
    ToolchainPreflightResult,
    check_toolchain_preflight,
    parse_toolchain_pins,
)


def test_parse_none_is_well_defined():
    pins = parse_toolchain_pins(None)
    assert isinstance(pins, ToolchainPins)
    assert pins.is_empty()


def test_parse_empty_string_is_well_defined():
    pins = parse_toolchain_pins("")
    assert isinstance(pins, ToolchainPins)
    assert pins.is_empty()


def test_parse_whitespace_only_is_well_defined():
    pins = parse_toolchain_pins("\n\t   \n")
    assert pins.is_empty()


def test_check_none_context_returns_ok_result():
    result = check_toolchain_preflight(None)
    assert isinstance(result, ToolchainPreflightResult)
    assert result.ok is True
    assert result.mismatches == []
    assert result.halt_message() == ""


def test_check_empty_context_returns_ok_result():
    result = check_toolchain_preflight("")
    assert isinstance(result, ToolchainPreflightResult)
    assert result.ok is True


def test_check_empty_pins_returns_ok_result():
    result = check_toolchain_preflight(pins=ToolchainPins())
    assert result.ok is True
    assert result.probes == []


def test_check_no_pins_halt_true_does_not_raise():
    # With nothing pinned, halt=True must still not raise — it's a pass.
    result = check_toolchain_preflight(None, halt=True)
    assert result.ok is True
