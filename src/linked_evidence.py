"""Load document links and fetch all linked source chunks for one case."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import chromadb

from src.retrieval import Citation, RetrievedEvidence


@dataclass(frozen=True)
class DocumentLink:
    case_id: str
    invoice_source: str
    po_numbers: tuple[str, ...]
    receipt_ids: tuple[str, ...]
    link_status: str
    link_note: str


def load_document_links(path: str | Path = "data/document_links.csv") -> dict[str, DocumentLink]:
    """Read source relationships only; evaluation labels are not part of this file."""
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result: dict[str, DocumentLink] = {}
    for row in rows:
        case_id = row.get("case_id", "").strip()
        if not case_id or case_id in result:
            raise ValueError("Document link file has a missing or duplicate case_id")
        result[case_id] = DocumentLink(
            case_id=case_id,
            invoice_source=row.get("invoice_source", "").strip(),
            po_numbers=tuple(value for value in row.get("po_numbers", "").split(";") if value),
            receipt_ids=tuple(value for value in row.get("receipt_ids", "").split(";") if value),
            link_status=row.get("link_status", "needs_review").strip(),
            link_note=row.get("link_note", "").strip(),
        )
    return result


def fetch_case_evidence(
    case_id: str,
    links: dict[str, DocumentLink],
    collection: chromadb.Collection,
) -> list[RetrievedEvidence]:
    """Fetch invoice, PO, and receipt chunks by exact IDs, failing closed on gaps."""
    link = links.get(case_id)
    if link is None:
        raise ValueError(f"No document link row exists for {case_id}")
    if link.link_status != "listed":
        raise ValueError(f"Document links for {case_id} need review: {link.link_note}")
    source_ids = [case_id, *link.po_numbers, *link.receipt_ids]
    fetched = collection.get(
        where={"source_id": {"$in": source_ids}},
        include=["documents", "metadatas"],
    )
    docs = fetched.get("documents") or []
    metadatas = fetched.get("metadatas") or []
    evidence: list[RetrievedEvidence] = []
    found: set[str] = set()
    for chunk_id, text, metadata in zip(fetched.get("ids") or [], docs, metadatas):
        if not isinstance(metadata, dict) or not isinstance(metadata.get("source_path"), str):
            raise ValueError(f"Linked chunk {chunk_id} is missing source provenance")
        source_id = str(metadata.get("source_id", ""))
        found.add(source_id)
        page = metadata.get("page_number")
        record_id = metadata.get("record_id")
        citation = Citation(
            source_path=metadata["source_path"],
            page_number=page if isinstance(page, int) else None,
            record_id=record_id if isinstance(record_id, str) else None,
        )
        citation.format()
        evidence.append(RetrievedEvidence(
            chunk_id=chunk_id,
            source_id=source_id,
            document_type=str(metadata.get("document_type", "unknown")),
            text=text or "",
            citation=citation,
            distance=0.0,
        ))
    missing = [source_id for source_id in source_ids if source_id not in found]
    if missing:
        raise ValueError(f"Linked evidence is not indexed for {case_id}: {', '.join(missing)}")
    return evidence
