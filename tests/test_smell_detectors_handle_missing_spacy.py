"""Tests for handle_missing_spacy_model — raises SpacyModelMissingError naming en_core_web_sm."""

from __future__ import annotations

import pytest

from bob3.spec_quality.smell_detectors import SpacyModelMissingError, handle_missing_spacy_model


class TestHandleMissingSpacyModel:
    def test_raises_spacy_model_missing_error(self):
        with pytest.raises(SpacyModelMissingError):
            handle_missing_spacy_model()

    def test_error_names_en_core_web_sm(self):
        with pytest.raises(SpacyModelMissingError) as exc_info:
            handle_missing_spacy_model()
        assert "en_core_web_sm" in str(exc_info.value)

    def test_error_is_exception_subclass(self):
        assert issubclass(SpacyModelMissingError, Exception)

    def test_error_message_is_not_empty(self):
        with pytest.raises(SpacyModelMissingError) as exc_info:
            handle_missing_spacy_model()
        assert str(exc_info.value).strip() != ""

    def test_spacy_model_missing_error_importable(self):
        from bob3.spec_quality.smell_detectors import SpacyModelMissingError as E
        assert E is SpacyModelMissingError
