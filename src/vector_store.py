"""Local Chroma storage for caller-supplied embeddings and provenance metadata."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Mapping, Sequence

import chromadb

from src.chunking import TextChunk


def _validate_inputs(
    chunks: Sequence[TextChunk], vectors: Sequence[Sequence[float]], dimensions: int
) -> None:
    if len(chunks) != len(vectors):
        raise ValueError("Each chunk must have exactly one embedding vector")
    if dimensions < 1:
        raise ValueError("dimensions must be positive")
    ids = [chunk.chunk_id for chunk in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError("Chunk IDs must be unique")
    for index, vector in enumerate(vectors):
        if len(vector) != dimensions:
            raise ValueError(f"Vector {index} has dimension {len(vector)}; expected {dimensions}")
        if any(not math.isfinite(value) for value in vector):
            raise ValueError(f"Vector {index} contains a non-finite value")


def rebuild_collection(
    persist_directory: str | Path,
    collection_name: str,
    chunks: Sequence[TextChunk],
    vectors: Sequence[Sequence[float]],
    *,
    embedding_model: str,
    dimensions: int,
) -> chromadb.Collection:
    """Replace one named local collection using explicit vectors and chunk provenance."""
    if not collection_name or not embedding_model:
        raise ValueError("collection_name and embedding_model are required")
    _validate_inputs(chunks, vectors, dimensions)

    client = chromadb.PersistentClient(path=str(persist_directory))
    existing = {collection.name for collection in client.list_collections()}
    if collection_name in existing:
        client.delete_collection(collection_name)
    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine", "embedding_model": embedding_model, "embedding_dimensions": dimensions},
        embedding_function=None,
    )
    if chunks:
        metadatas: list[Mapping[str, str | int]] = []
        for chunk in chunks:
            metadata: dict[str, str | int] = {
                "source_id": chunk.source_id,
                "source_path": chunk.source_path,
                "chunk_index": chunk.chunk_index,
                "document_type": chunk.document_type,
                "embedding_model": embedding_model,
            }
            if chunk.page_number > 0:
                metadata["page_number"] = chunk.page_number
            if chunk.record_id:
                metadata["record_id"] = chunk.record_id
            metadatas.append(metadata)
        collection.add(
            ids=[chunk.chunk_id for chunk in chunks],
            embeddings=[list(vector) for vector in vectors],
            metadatas=metadatas,
            documents=[chunk.text for chunk in chunks],
        )
    return collection


def query_by_embedding(
    collection: chromadb.Collection,
    vector: Sequence[float],
    *,
    n_results: int = 5,
    where: dict[str, object] | None = None,
) -> dict[str, object]:
    """Query with a caller-supplied vector and optional provenance filter."""
    if n_results < 1:
        raise ValueError("n_results must be positive")
    metadata = collection.metadata or {}
    dimensions = metadata.get("embedding_dimensions")
    if not isinstance(dimensions, int) or len(vector) != dimensions:
        raise ValueError(f"Query vector has dimension {len(vector)}; expected {dimensions}")
    if any(not math.isfinite(value) for value in vector):
        raise ValueError("Query vector contains a non-finite value")
    return collection.query(
        query_embeddings=[list(vector)],
        n_results=n_results,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
