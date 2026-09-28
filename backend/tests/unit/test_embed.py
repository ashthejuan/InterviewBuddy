"""Unit tests for local FastEmbed wrapper."""

from __future__ import annotations

from app.services.embed import embed_texts


def test_embed_texts_returns_384_dims() -> None:
    vectors = embed_texts(["Built billing API handling 2M req/day"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 384
    assert all(isinstance(x, float) for x in vectors[0][:3])


def test_embed_texts_empty() -> None:
    assert embed_texts([]) == []
