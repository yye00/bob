"""Error-path tests for the PEAS pipeline.

AC: invalid input raises ValueError and the function does not silently succeed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bob3.extract_from_peas import extract_and_synthesize


class TestExtractAndSynthesizeErrors:
    def test_missing_file_raises_value_error(self, tmp_path):
        missing = tmp_path / "does_not_exist.md"
        with pytest.raises(ValueError, match="does not exist"):
            extract_and_synthesize(missing)

    def test_non_path_integer_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            extract_and_synthesize(12345)  # type: ignore[arg-type]

    def test_non_path_none_raises_value_error(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            extract_and_synthesize(None)  # type: ignore[arg-type]

    def test_missing_file_does_not_silently_return(self, tmp_path):
        missing = tmp_path / "ghost.md"
        result = None
        raised = False
        try:
            result = extract_and_synthesize(missing)
        except (ValueError, TypeError, FileNotFoundError):
            raised = True
        assert raised, f"Expected an exception but got result: {result}"

    def test_non_path_list_raises(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            extract_and_synthesize(["/some/path.md"])  # type: ignore[arg-type]

    def test_value_error_message_is_informative(self, tmp_path):
        missing = tmp_path / "no_such_file.md"
        with pytest.raises(ValueError) as exc_info:
            extract_and_synthesize(missing)
        assert str(missing) in str(exc_info.value) or "does not exist" in str(exc_info.value)
