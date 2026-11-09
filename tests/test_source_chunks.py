import csv
import json

import pymupdf

from src.source_chunks import build_working_chunks


def make_invoice(path):
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Invoice 001, PO-2026-0101, total 25.00 USD")
    document.save(path)
    document.close()


def test_builds_chunks_from_allowlisted_sources_and_linked_records_not_ground_truth(tmp_path):
    raw = tmp_path / "raw"
    (raw / "invoices").mkdir(parents=True)
    (raw / "ground_truth").mkdir()
    make_invoice(raw / "invoices" / "001.pdf")
    (raw / "ground_truth" / "001.json").write_text('{"secret_label":"never ingest"}', encoding="utf-8")
    (raw / "purchase_orders.json").write_text(
        json.dumps([{"po_number": "PO-2026-0101", "currency": "USD", "lines": []}]), encoding="utf-8"
    )
    (raw / "receipts.json").write_text(
        json.dumps([{"receipt_id": "GR-00001", "po_number": "PO-2026-0101", "lines": []}]), encoding="utf-8"
    )
    scope = tmp_path / "working_set.csv"
    with scope.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["case_id", "invoice_source", "po_record_reference", "receipt_record_reference"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "case_id": "001_q01",
                "invoice_source": "invoices/001.pdf",
                "po_record_reference": "purchase_orders.json#PO-2026-0101",
                "receipt_record_reference": "receipts.json#GR-00001",
            }
        )

    chunks = build_working_chunks(scope, raw)

    by_type = {chunk.document_type: chunk for chunk in chunks}
    assert set(by_type) == {"invoice_pdf", "purchase_order", "goods_receipt"}
    assert by_type["invoice_pdf"].page_number == 1
    assert by_type["purchase_order"].record_id == "PO-2026-0101"
    assert by_type["goods_receipt"].record_id == "GR-00001"
    assert all("never ingest" not in chunk.text for chunk in chunks)
