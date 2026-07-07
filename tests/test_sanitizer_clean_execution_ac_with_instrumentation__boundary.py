"""Boundary tests for bob.sanitizer_clean_ac — empty/zero/minimum inputs.

Feature 1424c7e9-f248-4beb-b49d-2e407b609328.

Verifies that empty or minimal inputs return a well-defined result rather than
raising unexpected exceptions (the boundary case).
"""

from __future__ import annotations

from bob.sanitizer_clean_ac import (
    build_sanitizer_env,
    parse_sanitizer_clean_ac,
    scan_sanitizer_report,
)


class TestParseBoundary:
    def test_non_matching_line_returns_none(self):
        assert parse_sanitizer_clean_ac("integration: bob.ac_handler") is None

    def test_unrelated_empty_prefix_line_returns_none(self):
        assert parse_sanitizer_clean_ac("   ") is None

    def test_minimal_valid_ac_parses(self):
        assert parse_sanitizer_clean_ac("sanitizer-clean: asan x") == ("asan", "x")


class TestScanReportBoundary:
    def test_empty_string_returns_clean_true(self):
        assert scan_sanitizer_report("") is True

    def test_none_returns_clean_true(self):
        assert scan_sanitizer_report(None) is True

    def test_single_char_returns_clean_true(self):
        assert scan_sanitizer_report("x") is True


class TestEnvBoundary:
    def test_empty_base_env_returns_defined_dict(self):
        env = build_sanitizer_env("asan", {})
        assert isinstance(env, dict)
        assert "ASAN_OPTIONS" in env

    def test_none_base_env_returns_defined_dict(self):
        env = build_sanitizer_env("ubsan", None)
        assert isinstance(env, dict)
        assert "UBSAN_OPTIONS" in env
