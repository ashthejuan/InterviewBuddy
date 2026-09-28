"""Local FastEmbed embeddings (BAAI/bge-small-en-v1.5 → 384-d)."""

from __future__ import annotations

from functools import lru_cache

from fastembed import TextEmbedding

from app.config import get_settings


@lru_cache
def _model() -> TextEmbedding:
    settings = get_settings()
    return TextEmbedding(model_name=settings.embedding_model)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    vectors = list(_model().embed(texts))
    return [v.tolist() if hasattr(v, "tolist") else list(v) for v in vectors]
