"""Tests for the AC path-normalizer (feature d482fa32).

The AC synthesizer intermittently emits ``File exists:`` / ``pytest:`` path ACs
with corrupted paths that can never be satisfied. The normalizer canonicalizes
them to workspace-relative form BEFORE persistence:

  * strip a spurious leading ``/``     (``/src/bob/foo.py`` -> ``src/bob/foo.py``)
  * strip a spurious ``file.`` prefix  (``file.claude/hooks/x.py`` -> ``.claude/hooks/x.py``)
  * strip a spurious ``file:`` prefix  (``file:src/bob/foo.py`` -> ``src/bob/foo.py``)
  * collapse ``<pkg>/src/<pkg>`` duplication
  * de-duplicate against existing sibling ACs
"""

import pytest

from bob.ac_path_normalizer import normalize_path_ac, normalize_path_acs


class TestStripCorruption:
    def test_strips_leading_slash_on_file_exists(self):
        assert (
            normalize_path_ac("File exists: /src/bob/spec_synthesizer.py")
            == "File exists: src/bob/spec_synthesizer.py"
        )

    def test_strips_file_dot_prefix(self):
        assert (
            normalize_path_ac("File exists: file.claude/hooks/context_budget.py")
            == "File exists: .claude/hooks/context_budget.py"
        )

    def test_strips_file_colon_prefix(self):
        assert (
            normalize_path_ac("File exists: file:src/bob/foo.py")
            == "File exists: src/bob/foo.py"
        )

    def test_strips_leading_slash_on_pytest(self):
        assert (
            normalize_path_ac("pytest: /tests/test_foo.py")
            == "pytest: tests/test_foo.py"
        )

    def test_strips_file_colon_prefix_on_pytest(self):
        assert (
            normalize_path_ac("pytest: file:tests/test_foo.py")
            == "pytest: tests/test_foo.py"
        )

    def test_collapses_pkg_src_pkg_duplication(self):
        assert (
            normalize_path_ac("File exists: bob/src/bob/foo.py")
            == "File exists: src/bob/foo.py"
        )


class TestNoCorruption:
    def test_clean_file_exists_unchanged(self):
        ac = "File exists: src/bob/foo.py"
        assert normalize_path_ac(ac) == ac

    def test_clean_pytest_unchanged(self):
        ac = "pytest: tests/test_foo.py"
        assert normalize_path_ac(ac) == ac

    def test_non_path_ac_unchanged(self):
        ac = "Function defined: bob.foo.bar"
        assert normalize_path_ac(ac) == ac

    def test_integration_ac_unchanged(self):
        ac = "integration: bob.spec_synthesizer"
        assert normalize_path_ac(ac) == ac

    def test_pytest_with_selector_description_unchanged(self):
        ac = "pytest: tests/test_foo.py — empty input returns a result (boundary case)"
        # path token preserved, no leading slash to strip
        assert normalize_path_ac(ac) == ac


class TestListNormalizationAndDedup:
    def test_normalizes_each_ac_in_list(self):
        acs = [
            "File exists: /src/bob/spec_synthesizer.py",
            "File exists: file.claude/hooks/context_budget.py",
        ]
        out = normalize_path_acs(acs)
        assert "File exists: src/bob/spec_synthesizer.py" in out
        assert "File exists: .claude/hooks/context_budget.py" in out

    def test_dedupes_corrupted_against_clean_sibling(self):
        # F-R7-626 scenario: corrupted AC + correct sibling both present.
        acs = [
            "File exists: src/bob/spec_synthesizer.py",
            "File exists: /src/bob/spec_synthesizer.py",
        ]
        out = normalize_path_acs(acs)
        assert out == ["File exists: src/bob/spec_synthesizer.py"]

    def test_dedupes_file_dot_prefix_against_clean_sibling(self):
        # F-R7-603 scenario.
        acs = [
            "File exists: .claude/hooks/context_budget.py",
            "File exists: file.claude/hooks/context_budget.py",
        ]
        out = normalize_path_acs(acs)
        assert out == ["File exists: .claude/hooks/context_budget.py"]

    def test_preserves_order_and_non_path_acs(self):
        acs = [
            "File exists: /src/bob/foo.py",
            "Function defined: bob.foo.bar",
            "pytest: tests/test_foo.py",
        ]
        out = normalize_path_acs(acs)
        assert out == [
            "File exists: src/bob/foo.py",
            "Function defined: bob.foo.bar",
            "pytest: tests/test_foo.py",
        ]

    def test_distinct_paths_not_merged(self):
        acs = [
            "File exists: src/bob/a.py",
            "File exists: src/bob/b.py",
        ]
        out = normalize_path_acs(acs)
        assert len(out) == 2
