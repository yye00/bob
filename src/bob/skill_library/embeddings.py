"""Embedding backend selection for the skill library (F-R7-477).

Controls which sentence embedding model is used for similarity search
over the skill library. Defaults to sentence-transformers/all-MiniLM-L6-v2
but can be overridden via the BOB_SKILL_LIBRARY_EMBED_MODEL env var.
"""

from __future__ import annotations

import logging
import os
from typing import Sequence

import numpy as np

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_ENV_VAR = "BOB_SKILL_LIBRARY_EMBED_MODEL"

# Cached embedding instance to avoid repeated model loads
_embedding_instance = None
_loaded_model_name: str | None = None


def default_backend() -> str:
    """Return the default embedding model name.

    Returns:
        "sentence-transformers/all-MiniLM-L6-v2"
    """
    return _DEFAULT_MODEL


def load_from_env() -> str:
    """Return the embedding backend name, honouring BOB_SKILL_LIBRARY_EMBED_MODEL.

    Returns:
        Value of env var BOB_SKILL_LIBRARY_EMBED_MODEL if set, else default_backend().
    """
    return os.environ.get(_ENV_VAR, _DEFAULT_MODEL)


def _fastembed_model_name(backend: str) -> str:
    """Map a backend name to a fastembed-compatible model name.

    fastembed uses BAAI/* names internally; we translate the HuggingFace
    sentence-transformers name to the fastembed equivalent.
    """
    mapping = {
        "sentence-transformers/all-MiniLM-L6-v2": "BAAI/bge-small-en-v1.5",
    }
    return mapping.get(backend, backend)


def _get_embedding_model(backend: str | None = None):
    """Return a cached fastembed TextEmbedding instance.

    Args:
        backend: Model name (uses load_from_env() if None).

    Raises:
        ImportError: If fastembed is not installed.
        ValueError: If the backend module is not installed or invalid.
    """
    global _embedding_instance, _loaded_model_name

    if backend is None:
        backend = load_from_env()

    try:
        from fastembed import TextEmbedding  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            f"fastembed is required for the skill library embedding backend. "
            f"Install it with: pip install fastembed. Original error: {exc}"
        ) from exc

    fastembed_name = _fastembed_model_name(backend)

    if _embedding_instance is None or _loaded_model_name != fastembed_name:
        try:
            _embedding_instance = TextEmbedding(fastembed_name)
            _loaded_model_name = fastembed_name
        except Exception as exc:
            raise ValueError(
                f"Failed to load embedding backend {backend!r} "
                f"(fastembed model {fastembed_name!r}). "
                f"Ensure the backend is installed. Error: {exc}"
            ) from exc

    return _embedding_instance


def embed_texts(texts: Sequence[str], backend: str | None = None) -> np.ndarray:
    """Embed a list of texts using the configured backend.

    Args:
        texts: Texts to embed.
        backend: Override the backend (defaults to load_from_env()).

    Returns:
        2-D numpy array of shape (len(texts), dim).

    Raises:
        ValueError: If the backend is not installed or invalid.
    """
    model = _get_embedding_model(backend)
    embeddings = list(model.embed(texts))
    return np.array(embeddings)


def cosine_similarity_scores(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Return cosine similarity between a query vector and each row of matrix.

    Args:
        query_vec: 1-D embedding vector.
        matrix: 2-D matrix where each row is an embedding.

    Returns:
        1-D array of similarity scores in [-1, 1].
    """
    if matrix.shape[0] == 0:
        return np.array([], dtype=np.float32)

    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    matrix_norms = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10)
    return (matrix_norms @ query_norm).astype(np.float32)
