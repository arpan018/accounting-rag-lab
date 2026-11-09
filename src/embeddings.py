"""Small local Ollama embedding client that returns explicit vectors."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class EmbeddingError(RuntimeError):
    """Raised when Ollama cannot return the expected embedding vectors."""


@dataclass(frozen=True)
class EmbeddingConfig:
    base_url: str
    model: str
    dimensions: int
    timeout_seconds: int = 120


class OllamaEmbedder:
    # Restrict the client to the loopback machine; never route accounting text remotely.
    def __init__(self, config: EmbeddingConfig) -> None:
        endpoint = urlsplit(config.base_url)
        if endpoint.scheme != "http" or endpoint.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("Only a local Ollama endpoint is allowed")
        if not config.model or config.dimensions < 1:
            raise ValueError("Model name and positive vector dimensions are required")
        self.config = config

    # Send a batch with truncation disabled so missing context is reported, not hidden.
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if isinstance(texts, (str, bytes)) or not texts:
            raise ValueError("texts must be a non-empty sequence of strings")
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("every embedding input must be a non-empty string")

        payload = {"model": self.config.model, "input": list(texts), "truncate": False}
        request = Request(
            f"{self.config.base_url.rstrip('/')}/api/embed",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise EmbeddingError(f"Ollama embedding request failed: {exc}") from exc

        # Validate the model response before any vector reaches the index.
        vectors = result.get("embeddings") if isinstance(result, dict) else None
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise EmbeddingError("Ollama returned a different number of vectors than inputs")
        checked: list[list[float]] = []
        for index, vector in enumerate(vectors):
            if not isinstance(vector, list) or len(vector) != self.config.dimensions:
                actual = len(vector) if isinstance(vector, list) else "invalid"
                raise EmbeddingError(f"Vector {index} has dimension {actual}; expected {self.config.dimensions}")
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in vector):
                raise EmbeddingError(f"Vector {index} contains a non-finite or non-numeric value")
            checked.append([float(value) for value in vector])
        return checked
