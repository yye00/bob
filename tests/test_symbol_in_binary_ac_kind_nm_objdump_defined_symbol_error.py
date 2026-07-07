"""Error-path tests: invalid input raises ValueError, no silent success.

Feature 4a9a1f61 — symbol-in-binary AC kind.
"""

from __future__ import annotations

import pytest

from bob.ac_kinds import symbol_in_binary as sib


@pytest.mark.parametrize("bad", [None, 123, 4.5, [], {}, object()])
def test_parse_symbol_ac_rejects_non_str(bad):
    with pytest.raises(ValueError):
        sib.parse_symbol_ac(bad)


@pytest.mark.parametrize("bad", [None, 123, 4.5, [], {}, object()])
def test_check_symbol_rejects_non_str(bad):
    with pytest.raises(ValueError):
        sib.check_symbol_defined_in_binary(bad)


def test_check_empty_string_raises():
    with pytest.raises(ValueError):
        sib.check_symbol_defined_in_binary("")


def test_check_whitespace_only_raises():
    with pytest.raises(ValueError):
        sib.check_symbol_defined_in_binary("   ")


def test_parse_empty_string_raises():
    with pytest.raises(ValueError):
        sib.parse_symbol_ac("")


def test_check_matching_prefix_but_no_symbol_raises():
    # This IS the symbol-in-binary kind (prefix matches) but is malformed —
    # a matched-but-invalid AC must raise rather than silently pass.
    with pytest.raises(ValueError):
        sib.check_symbol_defined_in_binary("symbol defined in binary: libx.so")
