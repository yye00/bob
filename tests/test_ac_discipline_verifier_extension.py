"""Tests for hippy.spec_extraction AC discipline rule.

Verifier-extension features MUST NOT express behavior ACs. When a feature's
primary diff target is a VERIFIER_EXTENSION_MODULES path, every AC line
starting with 'behavior:' is rejected (demoted with a note) and a warning is
emitted. Non-verifier-extension features pass through unchanged.
"""

from __future__ import annotations

import logging

import pytest

from hippy.spec_extraction import (
    is_verifier_extension_target,
    reject_behavior_ac_for_verifier_extension,
)


VE_TARGET = "src/bob/enhanced_verification.py"
NORMAL_TARGET = "src/bob/models.py"


def test_is_verifier_extension_target_true():
    assert is_verifier_extension_target(VE_TARGET) is True


def test_is_verifier_extension_target_substring_match():
    assert is_verifier_extension_target("a/b/" + VE_TARGET) is True


def test_is_verifier_extension_target_false():
    assert is_verifier_extension_target(NORMAL_TARGET) is False


def test_reject_demotes_behavior_ac_for_verifier_extension(caplog):
    acs = [
        "behavior: foo does bar when baz",
        "File exists: src/x.py",
        "pytest: tests/test_x.py",
    ]
    with caplog.at_level(logging.WARNING):
        result = reject_behavior_ac_for_verifier_extension(acs, VE_TARGET)

    assert result.is_verifier_extension is True
    assert len(result.demoted) == 1
    assert result.demoted[0].original == "behavior: foo does bar when baz"
    # Non-behavior ACs preserved verbatim.
    assert "File exists: src/x.py" in result.filtered_acs
    assert "pytest: tests/test_x.py" in result.filtered_acs
    # Behavior AC replaced by a skip note, not kept verbatim.
    assert "behavior: foo does bar when baz" not in result.filtered_acs
    assert any("verifier-extension" in line for line in result.filtered_acs)
    # Warning emitted.
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_reject_passthrough_for_normal_feature():
    acs = ["behavior: foo does bar when baz", "File exists: src/x.py"]
    result = reject_behavior_ac_for_verifier_extension(acs, NORMAL_TARGET)

    assert result.is_verifier_extension is False
    assert result.demoted == []
    assert result.filtered_acs == acs


def test_reject_multiple_behavior_acs():
    acs = [
        "behavior: a does b",
        "BEHAVIOR: c does d",  # case-insensitive
        "structural: file contains X",
    ]
    result = reject_behavior_ac_for_verifier_extension(acs, VE_TARGET)
    assert len(result.demoted) == 2
    assert "structural: file contains X" in result.filtered_acs
