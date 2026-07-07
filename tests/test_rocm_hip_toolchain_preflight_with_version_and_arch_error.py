"""Error-path tests: invalid input raises ValueError; no silent success."""

from __future__ import annotations

import pytest

from bob.toolchain_preflight import (
    ToolchainPins,
    ToolchainPreflightError,
    check_toolchain_preflight,
    compare_semver,
    parse_semver,
    parse_toolchain_pins,
)


def test_error_is_value_error_subclass():
    assert issubclass(ToolchainPreflightError, ValueError)


def test_parse_pins_non_string_raises_value_error():
    with pytest.raises(ValueError):
        parse_toolchain_pins(3.14)  # type: ignore[arg-type]


def test_parse_pins_list_raises():
    with pytest.raises(ToolchainPreflightError):
        parse_toolchain_pins(["ROCm 7.2.1"])  # type: ignore[arg-type]


def test_parse_semver_non_string_raises():
    with pytest.raises(ValueError):
        parse_semver(None)  # type: ignore[arg-type]


def test_parse_semver_no_digits_raises():
    with pytest.raises(ToolchainPreflightError):
        parse_semver("gfxABC")


def test_compare_semver_bad_pin_raises():
    with pytest.raises(ToolchainPreflightError):
        compare_semver("7.2.1", "no-version")


def test_check_invalid_pins_type_raises_value_error():
    with pytest.raises(ValueError):
        check_toolchain_preflight(pins=42)  # type: ignore[arg-type]


def test_check_halt_true_raises_on_mismatch_no_silent_success():
    pins = ToolchainPins(rocm="7.2.1")
    with pytest.raises(ToolchainPreflightError):
        check_toolchain_preflight(
            pins=pins,
            halt=True,
            read_file=lambda p: "6.4.0\n",
            probe_archs=lambda: (True, []),
        )
