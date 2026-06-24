"""Tests for synthesizer File-exists AC emission for .py paths named in descriptions.

Verifies that:
(1) emit_file_exists_acs / _ensure_described_files_covered emits File-exists ACs
    for every concrete .py path named in a feature description.
(2) Duplicate File-exists ACs are NOT added when the path is already covered.
(3) Descriptions with no concrete .py paths are unaffected.
(4) integration: bob.synthesizer — the synthesizer module is importable and
    exposes emit_file_exists_acs.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ---------------------------------------------------------------------------
# Integration: bob.synthesizer
# ---------------------------------------------------------------------------

class TestBobSynthesizerIntegration:
    """AC: integration: bob.synthesizer"""

    def test_synthesizer_importable(self):
        mod = importlib.import_module("bob.synthesizer")
        assert mod is not None

    def test_emit_file_exists_acs_exported(self):
        from bob.synthesizer import emit_file_exists_acs
        assert callable(emit_file_exists_acs)


# ---------------------------------------------------------------------------
# emit_file_exists_acs behaviour tests
# ---------------------------------------------------------------------------

class TestEmitFileExistsAcs:
    """AC: pytest: tests/test_synthesizer_file_exists_ac.py"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from bob.synthesizer import emit_file_exists_acs
        self.fn = emit_file_exists_acs

    def test_emits_file_exists_for_described_path(self):
        """Description naming src/bob/brownfield/survey.py → File-exists AC emitted."""
        description = "Implement src/bob/brownfield/survey.py to scan the codebase."
        acs_in: list[str] = []
        result = self.fn(acs_in, description)
        assert any("File exists: src/bob/brownfield/survey.py" in ac for ac in result), (
            f"Expected 'File exists: src/bob/brownfield/survey.py' in ACs; got {result}"
        )

    def test_does_not_duplicate_existing_file_exists_ac(self):
        """If File-exists AC for the path already exists, it must NOT be added again."""
        description = "Implement src/bob/brownfield/survey.py."
        acs_in = ["File exists: src/bob/brownfield/survey.py"]
        result = self.fn(acs_in, description)
        matching = [ac for ac in result if "src/bob/brownfield/survey.py" in ac]
        assert len(matching) == 1, (
            f"Expected exactly 1 File-exists AC for survey.py, got {len(matching)}: {matching}"
        )

    def test_description_without_py_paths_unaffected(self):
        """Descriptions with no concrete .py paths must not add any File-exists ACs."""
        description = "Improve the retry logic and add better error messages."
        acs_in = ["pytest: tests/test_retry.py"]
        result = self.fn(acs_in, description)
        file_exists_acs = [ac for ac in result if ac.lower().startswith("file exists:")]
        assert file_exists_acs == [], (
            f"No .py paths in description — no File-exists ACs should be added; got {file_exists_acs}"
        )

    def test_emits_multiple_file_exists_for_multiple_paths(self):
        """Description naming two .py paths → two File-exists ACs emitted."""
        description = (
            "Implement src/bob/brownfield/survey.py and tools/spec_quality_score.py."
        )
        acs_in: list[str] = []
        result = self.fn(acs_in, description)
        assert any("src/bob/brownfield/survey.py" in ac for ac in result), (
            f"Expected File-exists for survey.py; got {result}"
        )
        assert any("tools/spec_quality_score.py" in ac for ac in result), (
            f"Expected File-exists for spec_quality_score.py; got {result}"
        )

    def test_bare_filename_without_directory_not_emitted(self):
        """Bare filenames without directory component must NOT generate File-exists ACs."""
        description = "See foo.py for implementation details."
        acs_in: list[str] = []
        result = self.fn(acs_in, description)
        file_exists_acs = [ac for ac in result if ac.lower().startswith("file exists:")]
        assert all("foo.py" not in ac for ac in file_exists_acs), (
            f"Bare 'foo.py' should not generate File-exists AC; got {file_exists_acs}"
        )

    def test_original_acs_preserved(self):
        """Original ACs are preserved after injection."""
        description = "Implement src/bob/bar.py."
        acs_in = ["pytest: tests/test_bar.py", "Function defined: bob.bar.run"]
        result = self.fn(acs_in, description)
        assert "pytest: tests/test_bar.py" in result
        assert "Function defined: bob.bar.run" in result

    def test_empty_description_returns_input_unchanged(self):
        """Empty description must return original ACs unchanged."""
        acs_in = ["pytest: tests/test_foo.py"]
        result = self.fn(acs_in, "")
        assert result == acs_in

    def test_empty_acs_and_description_with_path(self):
        """Empty ACs + description with path → File-exists AC added."""
        description = "Implement src/bob/alpha.py."
        result = self.fn([], description)
        assert any("src/bob/alpha.py" in ac for ac in result)


# ---------------------------------------------------------------------------
# Scorer integration: described .py path credited when File-exists AC present
# ---------------------------------------------------------------------------

class TestScorerCreditsDescribedPyPath:
    """AC: pytest: tests/test_synthesizer_file_exists_ac.py (scorer integration)"""

    def test_scorer_credits_file_exists_for_described_path(self):
        """contract_completeness > 0 when description names .py path that is covered by File-exists AC."""
        from tools.spec_quality_score import compute

        description = "Implement src/bob/brownfield/survey.py to scan the codebase."
        acs = [
            "File exists: src/bob/brownfield/survey.py",
            "pytest: tests/test_survey_boundary.py — boundary",
            "pytest: tests/test_survey_error.py — error",
        ]
        result = compute(name="Survey feature", description=description, acceptance_criteria=acs)
        assert result.contract_completeness > 0.0, (
            f"survey.py is covered by File-exists AC; contract_completeness={result.contract_completeness}"
        )

    def test_scorer_does_not_treat_prose_words_as_api_surfaces(self):
        """Prose words like 'defined', 'name', 'gate', 'correctly' must not be API surfaces."""
        from tools.spec_quality_score import compute

        description = (
            "A function defined: my_func() — it returns results correctly and "
            "handles failures. The gate name is checked."
        )
        acs = [
            "Function defined: spec_quality_score.my_func",
            "pytest: tests/test_my_feature_boundary.py — boundary",
            "pytest: tests/test_my_feature_error.py — error",
        ]
        result = compute(name="Test feature", description=description, acceptance_criteria=acs)
        assert result.contract_completeness > 0.0, (
            f"Prose words must not zero contract_completeness; got {result.contract_completeness}"
        )
