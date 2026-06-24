"""Tests: module_set() returns exactly 8 canonical section names."""

from __future__ import annotations

from bob3.spec_quality.section_selector import module_set


_EXPECTED_SECTIONS = {
    "functional",
    "perf",
    "security",
    "error_handling",
    "observability",
    "ops",
    "ux",
    "compat",
}


class TestModuleSetHasEight:
    def test_returns_list(self):
        result = module_set()
        assert isinstance(result, list)

    def test_has_exactly_eight_elements(self):
        assert len(module_set()) == 8

    def test_contains_all_expected_sections(self):
        assert set(module_set()) == _EXPECTED_SECTIONS

    def test_no_duplicates(self):
        result = module_set()
        assert len(result) == len(set(result))

    def test_contains_functional(self):
        assert "functional" in module_set()

    def test_contains_perf(self):
        assert "perf" in module_set()

    def test_contains_security(self):
        assert "security" in module_set()

    def test_contains_error_handling(self):
        assert "error_handling" in module_set()

    def test_contains_observability(self):
        assert "observability" in module_set()

    def test_contains_ops(self):
        assert "ops" in module_set()

    def test_contains_ux(self):
        assert "ux" in module_set()

    def test_contains_compat(self):
        assert "compat" in module_set()

    def test_returns_new_list_each_call(self):
        a = module_set()
        b = module_set()
        assert a == b
        assert a is not b  # independent copies
