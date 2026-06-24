"""Boundary tests for Full 22-smell linter extension to F-R7-410.

Verifies that empty, zero, or minimum input returns a well-defined result
rather than raising (boundary case).
"""

from __future__ import annotations

from bob.linter import detect_smells, blocks_plan_create, detector_count


class TestBoundaryCases:
    def test_empty_string_returns_empty_list(self):
        findings = detect_smells("")
        assert findings == []
        assert blocks_plan_create(findings) is False

    def test_whitespace_only_returns_list(self):
        findings = detect_smells("   ")
        assert isinstance(findings, list)
        assert blocks_plan_create(findings) is False

    def test_single_char_returns_list(self):
        findings = detect_smells("a")
        assert isinstance(findings, list)

    def test_single_newline_no_crash(self):
        findings = detect_smells("\n")
        assert isinstance(findings, list)

    def test_null_peer_criteria_no_crash(self):
        findings = detect_smells("", peer_criteria=None)
        assert findings == []

    def test_empty_peer_criteria_list_no_crash(self):
        findings = detect_smells("", peer_criteria=[])
        assert findings == []

    def test_null_known_feature_ids_no_crash(self):
        findings = detect_smells("", known_feature_ids=None)
        assert findings == []

    def test_empty_known_feature_ids_set_no_crash(self):
        findings = detect_smells("", known_feature_ids=frozenset())
        assert findings == []

    def test_minimum_clean_ac_no_crash(self):
        findings = detect_smells("pytest: tests/test_foo.py")
        assert isinstance(findings, list)
        assert blocks_plan_create(findings) is False

    def test_detector_count_with_empty_input(self):
        detect_smells("")
        assert detector_count() == 22

    def test_all_args_none_no_crash(self):
        findings = detect_smells("", peer_criteria=None, known_feature_ids=None)
        assert isinstance(findings, list)

    def test_unicode_input_no_crash(self):
        findings = detect_smells("日本語テスト")
        assert isinstance(findings, list)

    def test_very_long_whitespace_no_crash(self):
        findings = detect_smells("   " * 1000)
        assert isinstance(findings, list)
