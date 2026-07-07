"""Tests for bob.toolchain_preflight — ROCm/HIP toolchain version/arch pinning."""

from __future__ import annotations

import pytest

from bob.toolchain_preflight import (
    ToolchainPins,
    ToolchainPreflightError,
    ToolchainPreflightResult,
    check_toolchain_preflight,
    compare_semver,
    parse_semver,
    parse_toolchain_pins,
)


# ---------------------------------------------------------------------------
# parse_toolchain_pins
# ---------------------------------------------------------------------------


def test_parse_rocm_and_arch():
    pins = parse_toolchain_pins("Build RCCL against ROCm 7.2.1 for gfx942.")
    assert pins.rocm == "7.2.1"
    assert pins.archs == ["gfx942"]


def test_parse_cmake_and_hip():
    pins = parse_toolchain_pins("Requires cmake >=3.25 and HIP 7.2 toolchain.")
    assert pins.cmake == "3.25"
    assert pins.hip == "7.2"


def test_parse_rocm_colon_form():
    pins = parse_toolchain_pins("ROCm: 6.4")
    assert pins.rocm == "6.4"


def test_parse_multiple_archs_deduped():
    pins = parse_toolchain_pins("Targets gfx942 and gfx90a plus gfx942 again")
    assert pins.archs == ["gfx942", "gfx90a"]


def test_parse_none_returns_empty_pins():
    pins = parse_toolchain_pins(None)
    assert isinstance(pins, ToolchainPins)
    assert pins.is_empty()


def test_parse_empty_string_returns_empty_pins():
    pins = parse_toolchain_pins("   ")
    assert pins.is_empty()


def test_parse_no_pins_in_prose():
    pins = parse_toolchain_pins("This spec has no toolchain requirements.")
    assert pins.is_empty()


def test_parse_non_string_raises():
    with pytest.raises(ToolchainPreflightError):
        parse_toolchain_pins(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# semver helpers
# ---------------------------------------------------------------------------


def test_parse_semver_full():
    assert parse_semver("7.2.1") == (7, 2, 1)


def test_parse_semver_partial_defaults_zero():
    assert parse_semver("3.25") == (3, 25, 0)
    assert parse_semver("7") == (7, 0, 0)


def test_parse_semver_embedded():
    assert parse_semver("cmake version 3.27.4") == (3, 27, 4)


def test_parse_semver_no_number_raises():
    with pytest.raises(ToolchainPreflightError):
        parse_semver("no digits here")


def test_compare_semver_equal_when_pin_shorter():
    # pin "3.25" treats "3.25.7" as equal (>= satisfied)
    assert compare_semver("3.25.7", "3.25") == 0


def test_compare_semver_less_and_greater():
    assert compare_semver("3.24.0", "3.25") == -1
    assert compare_semver("3.26.0", "3.25") == 1
    assert compare_semver("7.2.1", "7.2.1") == 0


# ---------------------------------------------------------------------------
# check_toolchain_preflight
# ---------------------------------------------------------------------------


def test_check_no_pins_is_ok():
    result = check_toolchain_preflight(None)
    assert isinstance(result, ToolchainPreflightResult)
    assert result.ok is True
    assert result.mismatches == []


def test_check_rocm_match_ok():
    pins = ToolchainPins(rocm="7.2.1")
    result = check_toolchain_preflight(
        pins=pins,
        read_file=lambda p: "7.2.1\n",
        probe_archs=lambda: (True, []),
    )
    # hipcc probe will fail on host without hipcc; but rocm itself matches.
    # We only assert the rocm mismatch is absent.
    rocm_mismatches = [m for m in result.mismatches if "ROCm version mismatch" in m]
    assert rocm_mismatches == []


def test_check_rocm_version_mismatch_reported():
    pins = ToolchainPins(rocm="7.2.1")
    result = check_toolchain_preflight(
        pins=pins,
        read_file=lambda p: "6.4.0\n",
        probe_archs=lambda: (True, []),
    )
    assert result.ok is False
    assert any("ROCm version mismatch" in m for m in result.mismatches)


def test_check_rocm_missing_reported():
    pins = ToolchainPins(rocm="7.2.1")
    result = check_toolchain_preflight(
        pins=pins,
        read_file=lambda p: None,
        probe_archs=lambda: (True, []),
    )
    assert result.ok is False
    assert any("no ROCm install found" in m for m in result.mismatches)


def test_check_arch_missing_reported():
    pins = ToolchainPins(archs=["gfx942"])
    result = check_toolchain_preflight(
        pins=pins,
        read_file=lambda p: None,
        probe_archs=lambda: (True, ["gfx90a"]),
    )
    assert result.ok is False
    assert any("gfx942" in m and "not" in m for m in result.mismatches)


def test_check_arch_present_ok():
    pins = ToolchainPins(archs=["gfx942"])
    result = check_toolchain_preflight(
        pins=pins,
        read_file=lambda p: None,
        probe_archs=lambda: (True, ["gfx942", "gfx90a"]),
    )
    assert result.ok is True
    assert result.mismatches == []


def test_check_arch_rocminfo_unavailable_reported():
    pins = ToolchainPins(archs=["gfx942"])
    result = check_toolchain_preflight(
        pins=pins,
        read_file=lambda p: None,
        probe_archs=lambda: (False, []),
    )
    assert result.ok is False
    assert any("rocminfo" in m for m in result.mismatches)


def test_check_halt_raises_on_failure():
    pins = ToolchainPins(archs=["gfx942"])
    with pytest.raises(ToolchainPreflightError):
        check_toolchain_preflight(
            pins=pins,
            halt=True,
            read_file=lambda p: None,
            probe_archs=lambda: (True, ["gfx90a"]),
        )


def test_check_halt_message_names_the_problem():
    pins = ToolchainPins(rocm="7.2.1")
    result = check_toolchain_preflight(
        pins=pins,
        read_file=lambda p: "6.4.0\n",
        probe_archs=lambda: (True, []),
    )
    msg = result.halt_message()
    assert "7.2.1" in msg
    assert "6.4.0" in msg


def test_check_invalid_pins_type_raises():
    with pytest.raises(ToolchainPreflightError):
        check_toolchain_preflight(pins="not-a-pins")  # type: ignore[arg-type]
