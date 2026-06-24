"""Tests that handle_mutmut_unavailable raises MutmutMissingError with message
containing "mutmut" when package missing — AC-20 (error path).
"""

from __future__ import annotations

import pytest
from unittest.mock import patch

from bob.verification.mutation_gate import (
    MutmutMissingError,
    handle_mutmut_unavailable,
    run_mutation_test,
)


class TestHandleMutmutUnavailable:
    def test_raises_mutmut_missing_error(self):
        with pytest.raises(MutmutMissingError):
            handle_mutmut_unavailable()

    def test_error_message_contains_mutmut(self):
        with pytest.raises(MutmutMissingError) as exc_info:
            handle_mutmut_unavailable()
        assert "mutmut" in str(exc_info.value).lower()

    def test_error_is_runtime_error_subclass(self):
        with pytest.raises(RuntimeError):
            handle_mutmut_unavailable()

    def test_mutmut_missing_error_is_runtime_error(self):
        assert issubclass(MutmutMissingError, RuntimeError)

    def test_run_mutation_test_raises_when_mutmut_not_on_path(self, tmp_path):
        with patch("bob.verification.mutation_gate.shutil.which", return_value=None):
            with pytest.raises(MutmutMissingError) as exc_info:
                run_mutation_test(
                    feature_id="test-missing",
                    src_files=[],
                    test_dir=tmp_path,
                    workspace=tmp_path,
                )
            assert "mutmut" in str(exc_info.value)

    def test_error_names_mutmut_package(self):
        with pytest.raises(MutmutMissingError) as exc_info:
            handle_mutmut_unavailable()
        error_msg = str(exc_info.value)
        assert "mutmut" in error_msg, (
            f"Error message must name the 'mutmut' package, got: {error_msg!r}"
        )
