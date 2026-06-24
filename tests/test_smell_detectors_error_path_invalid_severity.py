"""Tests that severity_of("ZZZ") raises KeyError with message containing 'unknown severity'."""

from __future__ import annotations

import pytest

from bob.spec_quality.smell_detectors import severity_of


class TestSeverityOfInvalidSmellId:
    def test_unknown_smell_id_raises_key_error(self):
        with pytest.raises(KeyError):
            severity_of("ZZZ")

    def test_error_message_contains_unknown_severity(self):
        with pytest.raises(KeyError, match="unknown severity"):
            severity_of("ZZZ")

    def test_lowercase_invalid_raises_key_error(self):
        with pytest.raises(KeyError):
            severity_of("s01")

    def test_empty_string_raises_key_error(self):
        with pytest.raises(KeyError):
            severity_of("")

    def test_out_of_range_id_raises_key_error(self):
        with pytest.raises(KeyError):
            severity_of("S99")

    def test_s00_raises_key_error(self):
        with pytest.raises(KeyError):
            severity_of("S00")
