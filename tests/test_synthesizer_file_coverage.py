"""Tests for bob.synthesizer.emit_file_exists_acs — file-coverage post-synthesis step.

Verifies that:
1. emit_file_exists_acs is importable from bob.synthesizer
2. When a description names a concrete .py path, a File exists: AC is emitted
3. Paths already covered by existing ACs are not double-added
4. Bare filenames without a directory component are not emitted
5. Descriptions with no concrete .py paths leave criteria unchanged
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob.synthesizer import emit_file_exists_acs


def test_emit_file_exists_acs_is_callable():
    """AC: Function defined: bob.synthesizer.emit_file_exists_acs"""
    assert callable(emit_file_exists_acs)


def test_emits_file_exists_for_named_py_path():
    """When description names src/bob/brownfield/survey.py, a File exists: AC is added."""
    description = "This feature lives in src/bob/brownfield/survey.py and extends the survey module."
    criteria = ["pytest: tests/test_something.py"]
    result = emit_file_exists_acs(criteria, description)
    assert any("File exists: src/bob/brownfield/survey.py" in ac for ac in result), (
        f"Expected 'File exists: src/bob/brownfield/survey.py' in result, got {result}"
    )


def test_does_not_double_add_already_covered_path():
    """If File exists: src/foo/bar.py is already in criteria, it is not added again."""
    description = "Implements src/foo/bar.py."
    criteria = ["File exists: src/foo/bar.py", "pytest: tests/test_bar.py"]
    result = emit_file_exists_acs(criteria, description)
    file_exists_count = sum(1 for ac in result if "File exists: src/foo/bar.py" in ac)
    assert file_exists_count == 1, (
        f"Expected exactly 1 'File exists: src/foo/bar.py', got {file_exists_count} in {result}"
    )


def test_bare_filename_without_directory_is_not_emitted():
    """Bare filenames like foo.py without a directory component are ambiguous and skipped."""
    description = "See foo.py for implementation details."
    criteria = ["pytest: tests/test_foo.py"]
    result = emit_file_exists_acs(criteria, description)
    assert not any("File exists: foo.py" in ac for ac in result), (
        f"Bare filename foo.py should not generate a File exists: AC, got {result}"
    )


def test_no_py_paths_leaves_criteria_unchanged():
    """When description has no .py paths, criteria list is returned unchanged."""
    description = "This feature improves performance by caching database queries."
    criteria = ["File exists: src/cache.py", "pytest: tests/test_cache.py"]
    result = emit_file_exists_acs(criteria, description)
    # src/cache.py is already in criteria, so no new ACs should be added
    assert set(result) == set(criteria) or len(result) == len(criteria)


def test_empty_description_leaves_criteria_unchanged():
    """Empty description produces no new File exists: ACs."""
    criteria = ["pytest: tests/test_something.py"]
    result = emit_file_exists_acs(criteria, "")
    assert "File exists:" not in " ".join(result).replace("pytest:", "")


def test_multiple_py_paths_emitted():
    """Multiple distinct .py paths in description each get a File exists: AC."""
    description = (
        "This feature modifies src/bob/synthesizer.py and "
        "also touches src/bob/spec_synthesizer.py."
    )
    criteria = []
    result = emit_file_exists_acs(criteria, description)
    assert any("src/bob/synthesizer.py" in ac for ac in result), (
        f"Expected File exists: for synthesizer.py in {result}"
    )
    assert any("src/bob/spec_synthesizer.py" in ac for ac in result), (
        f"Expected File exists: for spec_synthesizer.py in {result}"
    )


def test_survey_py_path_use_case():
    """Regression: src/bob/brownfield/survey.py is covered even if synthesis derived a different slug."""
    description = (
        "PEAS description. The implementation resides in "
        "src/bob/brownfield/survey.py which provides the survey index."
    )
    # Simulate: synthesizer produced a different file AC, not the exact path
    criteria = ["File exists: src/bob/brownfield/survey_index.py", "pytest: tests/test_survey.py"]
    result = emit_file_exists_acs(criteria, description)
    assert any("src/bob/brownfield/survey.py" in ac for ac in result), (
        f"survey.py should be covered even when synthesis derived a different slug; got {result}"
    )


def test_returns_list():
    """emit_file_exists_acs always returns a list."""
    result = emit_file_exists_acs([], "No paths here.")
    assert isinstance(result, list)
