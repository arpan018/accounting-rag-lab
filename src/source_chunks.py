"""Build retrieval chunks from the selected invoice, PO, and receipt sources only."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from src.chunking import TextChunk, chunk_pages
from src.extraction import extract_pdf


def build_working_chunks(working_set_csv: str | Path, raw_data_dir: str | Path) -> list[TextChunk]:
    """Read only allow-listed source files and linked PO/receipt records, never labels."""
    csv_path = Path(working_set_csv)
    raw_root = Path(raw_data_dir)
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    chunks: list[TextChunk] = []
    po_ids: set[str] = set()
    receipt_ids: set[str] = set()
    for row in rows:
        invoice_path = row["invoice_source"]
        extracted = extract_pdf(raw_root / invoice_path, source_id=row["case_id"])
        chunks.extend(chunk_pages(extracted.pages))
        for po_id in re.findall(r"PO-\d{4}-\d{4}", row.get("po_record_reference", "")):
            po_ids.add(po_id)
        for receipt_id in re.findall(r"GR-\d+", row.get("receipt_record_reference", "")):
            receipt_ids.add(receipt_id)

    po_path = raw_root / "purchase_orders.json"
    receipt_path = raw_root / "receipts.json"
    purchase_orders = {record["po_number"]: record for record in json.loads(po_path.read_text(encoding="utf-8"))}
    receipts = {record["receipt_id"]: record for record in json.loads(receipt_path.read_text(encoding="utf-8"))}

    for po_id in sorted(po_ids):
        record = purchase_orders.get(po_id)
        if record is not None:
            chunks.append(_record_chunk(po_id, po_path, record, "purchase_order"))
    for receipt_id in sorted(receipt_ids):
        record = receipts.get(receipt_id)
        if record is not None:
            chunks.append(_record_chunk(receipt_id, receipt_path, record, "goods_receipt"))
    return chunks


# Keep the structured record ID and source file as its citation locator.
def _record_chunk(record_id: str, source_path: Path, record: dict, document_type: str) -> TextChunk:
    text = json.dumps(record, ensure_ascii=False, sort_keys=True)
    return TextChunk(
        chunk_id=f"{document_type}:{record_id}:record",
        source_id=record_id,
        source_path=source_path.as_posix(),
        page_number=0,
        chunk_index=0,
        text=text,
        document_type=document_type,
        record_id=record_id,
    )
