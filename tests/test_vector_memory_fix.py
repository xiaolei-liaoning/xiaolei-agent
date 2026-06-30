import pytest
from core.memory.vector_memory import LocalEmbeddingFunction, SentenceTransformerEmbeddingFunction


def test_local_embedding_is_chromadb_compatible():
    emb_fn = LocalEmbeddingFunction()
    result = emb_fn(["hello world"])
    assert isinstance(result, list)
    assert all(isinstance(v, list) for v in result)
    assert all(isinstance(x, float) for v in result for x in v)
    assert len(result[0]) == 768


def test_local_embedding_has_dimensionality():
    emb_fn = LocalEmbeddingFunction()
    assert hasattr(emb_fn, "dimensionality")
    assert emb_fn.dimensionality == 768


def test_local_embedding_empty_input():
    emb_fn = LocalEmbeddingFunction()
    assert emb_fn([]) == []
    assert emb_fn(None) == []
    assert emb_fn([""])[0] == [0.0] * 768


def test_local_embedding_non_string_input():
    emb_fn = LocalEmbeddingFunction()
    result = emb_fn([123])
    assert isinstance(result, list)
    assert len(result[0]) == 768


def test_sentence_transformer_has_dimensionality():
    emb_fn = SentenceTransformerEmbeddingFunction(model_type="local")
    assert hasattr(emb_fn, "dimensionality")
    assert emb_fn.dimensionality == 768
