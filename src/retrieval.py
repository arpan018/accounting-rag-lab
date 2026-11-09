"""Retrieve evidence with source locators suitable for grounded answer citations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import chromadb

from src.embeddings import OllamaEmbedder
from src.vector_store import query_by_embedding


@dataclass(frozen=True)
class Citation:
    source_path: str
    page_number: int | None = None
    record_id: str | None = None

    # Use page citations for PDFs and stable record IDs for structured sources.
    def format(self) -> str:
        if self.page_number is not None:
            return f"{self.source_path}, page {self.page_number}"
        if self.record_id:
            return f"{self.source_path}, record {self.record_id}"
        raise ValueError("Citation requires a page number or record ID")


@dataclass(frozen=True)
class RetrievedEvidence:
    chunk_id: str
    source_id: str
    document_type: str
    text: str
    citation: Citation
    distance: float


# Embed the question once, then return only Chroma hits with traceable locators.
def retrieve_evidence(
    question: str,
    embedder: OllamaEmbedder,
    collection: chromadb.Collection,
    *,
    top_k: int = 5,
    where: Mapping[str, object] | None = None,
) -> list[RetrievedEvidence]:
    if not question.strip():
        raise ValueError("question must not be empty")
    query_vectors = embedder.embed([question])
    if len(query_vectors) != 1:
        raise ValueError("Embedder must return exactly one query vector")
    result = query_by_embedding(collection, query_vectors[0], n_results=top_k, where=dict(where) if where else None)

    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    evidence: list[RetrievedEvidence] = []
    for chunk_id, text, metadata, distance in zip(ids, documents, metadatas, distances):
        if not isinstance(metadata, dict) or not isinstance(metadata.get("source_path"), str):
            raise ValueError(f"Retrieved chunk {chunk_id} is missing source provenance")
        page = metadata.get("page_number")
        record_id = metadata.get("record_id")
        citation = Citation(
            source_path=metadata["source_path"],
            page_number=page if isinstance(page, int) else None,
            record_id=record_id if isinstance(record_id, str) else None,
        )
        # Fail closed when indexed metadata cannot identify a source location.
        citation.format()
        evidence.append(
            RetrievedEvidence(
                chunk_id=chunk_id,
                source_id=str(metadata.get("source_id", "")),
                document_type=str(metadata.get("document_type", "unknown")),
                text=text or "",
                citation=citation,
                distance=float(distance),
            )
        )
    return evidence
