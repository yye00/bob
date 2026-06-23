"""Tests for embedding similarity threshold gate-boundary value."""

from bob3.skill_library.registry import similarity_threshold
from bob3.skill_library.embeddings import default_backend, load_from_env


def test_similarity_threshold_exact_value():
    """similarity_threshold must return exactly 0.75 at the gate-boundary value."""
    assert similarity_threshold() == 0.75


def test_similarity_threshold_is_float():
    assert isinstance(similarity_threshold(), float)


def test_default_backend_returns_expected_model():
    assert default_backend() == "sentence-transformers/all-MiniLM-L6-v2"


def test_load_from_env_returns_default_when_env_not_set(monkeypatch):
    monkeypatch.delenv("BOB3_SKILL_LIBRARY_EMBED_MODEL", raising=False)
    assert load_from_env() == "sentence-transformers/all-MiniLM-L6-v2"


def test_load_from_env_honours_env_var(monkeypatch):
    monkeypatch.setenv("BOB3_SKILL_LIBRARY_EMBED_MODEL", "custom/model-name")
    assert load_from_env() == "custom/model-name"
