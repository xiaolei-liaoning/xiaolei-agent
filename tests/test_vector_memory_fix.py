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


def test_local_embedding_full_protocol():
    emb_fn = LocalEmbeddingFunction()
    assert emb_fn.name() == "local"
    config = emb_fn.get_config()
    assert isinstance(config, dict)
    assert config["dim"] == 768
    restored = LocalEmbeddingFunction.build_from_config(config)
    assert isinstance(restored, LocalEmbeddingFunction)
    assert restored.dimensionality == 768
    assert emb_fn.supported_spaces() == ["cosine", "l2", "ip"]
    assert emb_fn.default_space() == "cosine"
    emb_fn.validate_config({})
    emb_fn.validate_config_update({}, {})


def test_local_embedding_query_returns_batch():
    emb_fn = LocalEmbeddingFunction()
    result = emb_fn.embed_query("hello")
    assert isinstance(result, list)
    assert len(result) == 1
    assert len(result[0]) == 768
