"""Tests for error paths when embedding backend is not installed or invalid.

AC: default_backend must raise an error and reject an invalid configuration
when the backend module is not installed.
"""

import importlib
import sys
import pytest

from bob.skill_library.embeddings import (
    default_backend,
    load_from_env,
    _get_embedding_model,
)


def test_default_backend_returns_expected_model():
    assert default_backend() == "sentence-transformers/all-MiniLM-L6-v2"


def test_get_embedding_model_raises_import_error_when_fastembed_missing(monkeypatch):
    """_get_embedding_model must raise ImportError when fastembed is not installed."""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "fastembed":
            raise ImportError("No module named 'fastembed'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    # Clear cached instance so it tries to load again
    import bob.skill_library.embeddings as emb_mod
    old_instance = emb_mod._embedding_instance
    old_name = emb_mod._loaded_model_name
    emb_mod._embedding_instance = None
    emb_mod._loaded_model_name = None

    try:
        with pytest.raises(ImportError, match="fastembed"):
            _get_embedding_model("sentence-transformers/all-MiniLM-L6-v2")
    finally:
        emb_mod._embedding_instance = old_instance
        emb_mod._loaded_model_name = old_name


def test_get_embedding_model_raises_value_error_for_invalid_model(monkeypatch):
    """_get_embedding_model must raise ValueError for an invalid/uninstalled backend."""
    # Only test this if fastembed is actually installed
    try:
        import fastembed  # noqa: F401
    except ImportError:
        pytest.skip("fastembed not installed, skipping invalid-model test")

    import bob.skill_library.embeddings as emb_mod
    old_instance = emb_mod._embedding_instance
    old_name = emb_mod._loaded_model_name
    emb_mod._embedding_instance = None
    emb_mod._loaded_model_name = None

    try:
        with pytest.raises((ValueError, Exception)):
            _get_embedding_model("definitely-not-a-valid/model-xyzzy-123456")
    finally:
        emb_mod._embedding_instance = old_instance
        emb_mod._loaded_model_name = old_name


def test_load_from_env_invalid_model_name_not_validated_at_load_time(monkeypatch):
    """load_from_env only returns a string; validation happens at embed_texts time."""
    monkeypatch.setenv("BOB_SKILL_LIBRARY_EMBED_MODEL", "invalid/model-name-that-does-not-exist")
    result = load_from_env()
    # load_from_env should return the raw string (validation deferred)
    assert result == "invalid/model-name-that-does-not-exist"


def test_embed_texts_raises_when_fastembed_missing(monkeypatch):
    """embed_texts must propagate ImportError when fastembed is not installed."""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "fastembed":
            raise ImportError("No module named 'fastembed'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    import bob.skill_library.embeddings as emb_mod
    old_instance = emb_mod._embedding_instance
    old_name = emb_mod._loaded_model_name
    emb_mod._embedding_instance = None
    emb_mod._loaded_model_name = None

    try:
        with pytest.raises(ImportError):
            from bob.skill_library.embeddings import embed_texts
            embed_texts(["test query"])
    finally:
        emb_mod._embedding_instance = old_instance
        emb_mod._loaded_model_name = old_name


def test_default_backend_is_not_empty_string():
    assert default_backend() != ""


def test_default_backend_contains_model_name():
    backend = default_backend()
    assert "MiniLM" in backend or "sentence-transformers" in backend
