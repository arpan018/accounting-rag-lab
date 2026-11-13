"""Load document links and fetch all linked source chunks for one case."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import re

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


def resolve_invoice_input(invoice_path: str, links: dict[str, DocumentLink]) -> DocumentLink:
    """Resolve an allow-listed invoice by case ID, filename, or path."""
    supplied = _normalize_invoice_path(invoice_path)
    supplied_path = Path(supplied)
    supplied_aliases = {supplied, supplied_path.name, supplied_path.stem}
    matches = [
        link
        for link in links.values()
        if supplied_aliases.intersection(_invoice_aliases(link))
    ]
    if not matches:
        raise ValueError(f"Invoice path is not listed in data/document_links.csv: {invoice_path}")
    if len(matches) > 1:
        options = ", ".join(f"{link.case_id} ({link.invoice_source})" for link in matches)
        raise ValueError(f"Invoice name is ambiguous; use a full path. Matches: {options}")
    link = matches[0]
    _require_reviewed_link(link)
    return link


def resolve_po_input(po_number: str, links: dict[str, DocumentLink]) -> tuple[DocumentLink, ...]:
    """Resolve an exact PO and return its invoice candidates, if any."""
    if not re.fullmatch(r"PO-\d{4}-\d{4}", po_number):
        raise ValueError("PO number must use the format PO-YYYY-NNNN")
    matches = tuple(link for link in links.values() if po_number in link.po_numbers)
    if not matches:
        raise ValueError(f"No invoice link is listed for purchase order {po_number}")
    if any(link.link_status != "listed" for link in matches):
        notes = [f"{link.case_id}: {link.link_note or 'link needs review'}" for link in matches if link.link_status != "listed"]
        raise ValueError("PO link needs human review: " + "; ".join(notes))
    return matches


def _require_reviewed_link(link: DocumentLink) -> None:
    if link.link_status != "listed":
        raise ValueError(f"Document links for {link.case_id} need review: {link.link_note}")


def _normalize_invoice_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/").casefold()
    normalized = re.sub(r"^\./", "", normalized)
    marker = "/data/raw/invoice-agent/"
    if marker in normalized:
        normalized = normalized.rsplit(marker, 1)[1]
    elif normalized.startswith("data/raw/invoice-agent/"):
        normalized = normalized[len("data/raw/invoice-agent/"):]
    return normalized


def _invoice_aliases(link: DocumentLink) -> set[str]:
    """Return exact allow-list names, including the extensionless case ID."""
    source = _normalize_invoice_path(link.invoice_source)
    source_path = Path(source)
    return {
        source,
        source_path.name,
        source_path.stem,
        link.case_id.casefold(),
    }


def fetch_case_evidence(
    case_id: str,
    links: dict[str, DocumentLink],
    collection: chromadb.Collection,
) -> list[RetrievedEvidence]:
    """Fetch invoice, PO, and receipt chunks by exact IDs, failing closed on gaps."""
    link = links.get(case_id)
    if link is None:
        raise ValueError(f"No document link row exists for {case_id}")
    _require_reviewed_link(link)
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
