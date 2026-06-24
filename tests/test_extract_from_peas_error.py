"""Error-path tests for bob.extract_from_peas — invalid input raises ValueError."""
from __future__ import annotations

from pathlib import Path

import pytest

from bob.extract_from_peas import run_extraction_pipeline


class TestRunExtractionPipelineErrors:
    def test_missing_file_raises_value_error(self, tmp_path):
        missing = tmp_path / "nonexistent.md"
        with pytest.raises(ValueError):
            run_extraction_pipeline(missing)

    def test_non_path_integer_raises_value_error(self):
        with pytest.raises(ValueError):
            run_extraction_pipeline(42)  # type: ignore[arg-type]

    def test_non_path_none_raises_value_error(self):
        with pytest.raises(ValueError):
            run_extraction_pipeline(None)  # type: ignore[arg-type]

    def test_non_path_list_raises(self):
        with pytest.raises(ValueError):
            run_extraction_pipeline(["a", "b"])  # type: ignore[arg-type]

    def test_missing_file_does_not_silently_return(self, tmp_path):
        missing = tmp_path / "does_not_exist.md"
        raised = False
        try:
            run_extraction_pipeline(missing)
        except ValueError:
            raised = True
        assert raised, "run_extraction_pipeline should raise ValueError for missing file"

    def test_value_error_message_is_informative(self, tmp_path):
        missing = tmp_path / "gone.md"
        with pytest.raises(ValueError, match=r"(?i)peas|not exist|does not"):
            run_extraction_pipeline(missing)
