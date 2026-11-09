import json
from io import BytesIO
from unittest.mock import patch

import pytest

from src.embeddings import EmbeddingConfig, EmbeddingError, OllamaEmbedder


def response(payload):
    return BytesIO(json.dumps(payload).encode("utf-8"))


def make_embedder(dimensions=3):
    return OllamaEmbedder(EmbeddingConfig("http://127.0.0.1:11434", "embeddinggemma-2:270m", dimensions))


def test_sends_local_batch_and_disables_silent_truncation():
    with patch("src.embeddings.urlopen", return_value=response({"embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]})) as mocked:
        vectors = make_embedder().embed(["invoice total", "PO line"])

    request = mocked.call_args.args[0]
    body = json.loads(request.data)
    assert request.full_url == "http://127.0.0.1:11434/api/embed"
    assert body == {"model": "embeddinggemma-2:270m", "input": ["invoice total", "PO line"], "truncate": False}
    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]


def test_rejects_remote_endpoint_and_empty_input():
    with pytest.raises(ValueError, match="local Ollama"):
        OllamaEmbedder(EmbeddingConfig("https://example.com", "model", 3))
    with pytest.raises(ValueError, match="local Ollama"):
        OllamaEmbedder(EmbeddingConfig("http://127.0.0.1.evil", "model", 3))
    with pytest.raises(ValueError, match="non-empty"):
        make_embedder().embed([])


def test_rejects_wrong_vector_count_or_dimensions():
    with patch("src.embeddings.urlopen", return_value=response({"embeddings": [[0.1, 0.2, 0.3]]})):
        with pytest.raises(EmbeddingError, match="number of vectors"):
            make_embedder().embed(["one", "two"])

    with patch("src.embeddings.urlopen", return_value=response({"embeddings": [[0.1, 0.2]]})):
        with pytest.raises(EmbeddingError, match="expected 3"):
            make_embedder().embed(["one"])


def test_rejects_non_finite_vector_values():
    with patch("src.embeddings.urlopen", return_value=response({"embeddings": [[0.1, float("nan"), 0.3]]})):
        with pytest.raises(EmbeddingError, match="non-finite"):
            make_embedder().embed(["one"])
