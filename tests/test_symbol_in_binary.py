"""Tests for the symbol-in-binary AC kind (feature 4a9a1f61)."""

from __future__ import annotations

import shutil
import subprocess
import textwrap

import pytest

from bob.ac_kinds import symbol_in_binary as sib


# --------------------------------------------------------------------------- #
# parse_symbol_ac
# --------------------------------------------------------------------------- #
def test_parse_symbol_ac_basic():
    parsed = sib.parse_symbol_ac(
        "symbol defined in binary: librccl.so::ncclAllReduce"
    )
    assert parsed.artifact == "librccl.so"
    assert parsed.symbol == "ncclAllReduce"


def test_parse_symbol_ac_strips_whitespace():
    parsed = sib.parse_symbol_ac(
        "  symbol defined in binary:  build/librccl.so :: ncclAllReduce  "
    )
    assert parsed.artifact == "build/librccl.so"
    assert parsed.symbol == "ncclAllReduce"


def test_parse_symbol_ac_case_insensitive_prefix():
    parsed = sib.parse_symbol_ac(
        "Symbol Defined In Binary: libfoo.a::my_func"
    )
    assert parsed.artifact == "libfoo.a"
    assert parsed.symbol == "my_func"


def test_parse_symbol_ac_demangled_symbol():
    parsed = sib.parse_symbol_ac(
        "symbol defined in binary: libx.so::ns::Class::method(int)"
    )
    assert parsed.artifact == "libx.so"
    assert parsed.symbol == "ns::Class::method(int)"


def test_parse_symbol_ac_not_this_kind_returns_none():
    assert sib.parse_symbol_ac("Function defined: bob.foo.bar") is None
    assert sib.parse_symbol_ac("pytest: tests/test_x.py") is None


# --------------------------------------------------------------------------- #
# check_symbol_defined_in_binary — real compiled artifact
# --------------------------------------------------------------------------- #
def _have_toolchain() -> bool:
    return all(shutil.which(t) for t in ("cc", "nm"))


@pytest.fixture
def defined_lib(tmp_path):
    """Compile a shared library that DEFINES ``my_defined_symbol``."""
    src = tmp_path / "lib.c"
    src.write_text(
        textwrap.dedent(
            """
            int my_defined_symbol(int x) { return x + 1; }
            """
        )
    )
    lib = tmp_path / "libdefined.so"
    subprocess.run(
        ["cc", "-shared", "-fPIC", "-o", str(lib), str(src)],
        check=True,
    )
    return lib


@pytest.mark.skipif(not _have_toolchain(), reason="cc/nm not available")
def test_check_defined_symbol_passes(defined_lib):
    result = sib.check_symbol_defined_in_binary(
        f"symbol defined in binary: {defined_lib}::my_defined_symbol"
    )
    assert result.passed is True
    assert "my_defined_symbol" in result.evidence
    assert result.command  # the nm/objdump command was recorded


@pytest.mark.skipif(not _have_toolchain(), reason="cc/nm not available")
def test_check_undefined_symbol_fails(defined_lib):
    result = sib.check_symbol_defined_in_binary(
        f"symbol defined in binary: {defined_lib}::not_present_anywhere"
    )
    assert result.passed is False
    assert result.command  # evidence still persisted


@pytest.mark.skipif(not _have_toolchain(), reason="cc/nm not available")
def test_check_symbol_only_referenced_fails(tmp_path):
    """A symbol that is UNDEFINED (type U) must NOT count as defined."""
    src = tmp_path / "ref.c"
    src.write_text(
        textwrap.dedent(
            """
            extern int external_thing(int);
            int caller(int x) { return external_thing(x); }
            """
        )
    )
    obj = tmp_path / "ref.o"
    subprocess.run(["cc", "-c", "-fPIC", "-o", str(obj), str(src)], check=True)
    result = sib.check_symbol_defined_in_binary(
        f"symbol defined in binary: {obj}::external_thing"
    )
    # external_thing is referenced (U) but not defined (T/t) → must fail
    assert result.passed is False


def test_check_missing_artifact_returns_failed_result(tmp_path):
    missing = tmp_path / "nope.so"
    result = sib.check_symbol_defined_in_binary(
        f"symbol defined in binary: {missing}::whatever"
    )
    assert result.passed is False
    assert "not found" in result.reason.lower() or "missing" in result.reason.lower()


def test_check_returns_result_object():
    """The returned object exposes the documented fields."""
    result = sib.check_symbol_defined_in_binary(
        "symbol defined in binary: /definitely/missing.so::sym"
    )
    assert hasattr(result, "passed")
    assert hasattr(result, "reason")
    assert hasattr(result, "command")
    assert hasattr(result, "evidence")
