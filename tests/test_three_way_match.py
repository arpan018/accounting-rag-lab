"""T12d/T12e tests: deterministic invoice/PO/GR orchestration, both input modes, citations, and review gates."""

import csv
import json

import pymupdf
import pytest

from src.record_loader import SourceRecordLoader
from src.three_way_match import run_three_way_check


INVOICE_TEXT = """Example Vendor
INVOICE
Invoice No:
INV-1001
PO Number:
PO-2026-0101
Description
Qty
Unit Price
Amount
Copy paper
2
$10.00
$20.00
Subtotal
$20.00
Discount
$0.00
Tax
$0.00
Total Due
$20.00
"""


def make_loader(
    tmp_path, *, invoice_texts=None, receipt_quantities=None, no_po_review=False,
    po_description="Copy paper",
):
    """Build isolated source files that follow the dataset's PO/receipt JSON shapes."""
    invoice_texts = invoice_texts or {"001": INVOICE_TEXT}
    raw = tmp_path / "raw"
    (raw / "invoices").mkdir(parents=True)
    for case_id, text in invoice_texts.items():
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((72, 72), text)
        document.save(raw / "invoices" / f"{case_id}.pdf")
        document.close()
    po = {
        "po_number": "PO-2026-0101",
        "vendor": "Example Vendor",
        "currency": "USD",
        "receipt_required": True,
        "lines": [{"line_no": 1, "sku": "SKU-1", "description": po_description, "quantity": "2", "unit_price": "10.00"}],
    }
    (raw / "purchase_orders.json").write_text(json.dumps([po]), encoding="utf-8")
    quantities = receipt_quantities or ["2"]
    receipts = [
        {"receipt_id": f"GR-{index:05d}", "po_number": "PO-2026-0101", "date": "2026-03-02",
         "lines": [{"line_no": 1, "quantity": quantity}]}
        for index, quantity in enumerate(quantities, start=1)
    ]
    (raw / "receipts.json").write_text(json.dumps(receipts), encoding="utf-8")

    working = tmp_path / "working_set.csv"
    working_fields = ["case_id", "invoice_source", "po_record_reference", "receipt_record_reference"]
    with working.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=working_fields)
        writer.writeheader()
        for case_id in invoice_texts:
            writer.writerow({"case_id": case_id, "invoice_source": f"invoices/{case_id}.pdf",
                             "po_record_reference": "purchase_orders.json#PO-2026-0101",
                             "receipt_record_reference": ""})
    review = tmp_path / "review_queue.csv"
    review_fields = ["case_id", "owner_verified_po_gr_links", "owner_verified_expected_findings", "review_status"]
    with review.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=review_fields)
        writer.writeheader()
        for case_id in invoice_texts:
            writer.writerow({"case_id": case_id,
                             "owner_verified_po_gr_links": "Owner links PO-2026-0101" if no_po_review else "",
                             "owner_verified_expected_findings": "PO link is not printed" if no_po_review else "No discrepancy reported.",
                             "review_status": "reviewed"})
    return SourceRecordLoader(raw, working, review)


def test_invoice_input_completes_three_way_check_with_citations(tmp_path):
    loader = make_loader(tmp_path)

    result = run_three_way_check(invoice_path="invoices/001.pdf", loader=loader)

    assert result.status == "completed"
    assert result.invoice_case_id == "001"
    assert result.purchase_order.po_number == "PO-2026-0101"
    assert [item.receipt_id for item in result.receipt_records] == ["GR-00001"]
    assert result.findings == ()
    assert any("invoices/001.pdf, page 1" in citation for citation in result.citations)
    assert any("purchase_orders.json, record PO-2026-0101" in citation for citation in result.citations)
    assert any("receipts.json, record GR-00001" in citation for citation in result.citations)
    assert result.requires_human_review is False
    assert result.human_review_reasons == ()
    assert result.first_pass_review == "No discrepancy reported."
    assert result.as_dict()["line_match_summary"] == {
        "invoice_lines": 1,
        "linked_to_po": 1,
        "unresolved": 0,
    }
    assert "line_links" not in result.as_dict()


def test_missing_discount_is_calculation_note_not_extraction_warning(tmp_path):
    text = INVOICE_TEXT.replace("Discount\n$0.00\n", "")
    loader = make_loader(tmp_path, invoice_texts={"001": text})

    result = run_three_way_check(invoice_path="invoices/001.pdf", loader=loader)
    summary = result.as_dict()

    assert "discount_not_printed_zero_used_for_arithmetic_check" not in result.extraction_warnings
    assert result.calculation_notes == (
        "Invoice does not state a discount; arithmetic check assumes zero discount.",
    )
    assert summary["calculation_notes"] == list(result.calculation_notes)


def test_unique_quantity_price_mapping_shows_po_sku_without_false_review(tmp_path):
    loader = make_loader(tmp_path, po_description="White bond A4 paper, 500 sheets")

    result = run_three_way_check(invoice_path="invoices/001.pdf", loader=loader)
    summary = result.as_dict()

    assert result.findings == ()
    assert result.requires_human_review is False
    assert result.human_review_reasons == ()
    assert summary["line_match_summary"] == {
        "invoice_lines": 1,
        "linked_to_po": 1,
        "unresolved": 0,
    }
    assert "line_links" not in summary


def test_human_review_reasons_explain_duplicate_invoice_on_same_po(tmp_path):
    duplicate = INVOICE_TEXT.replace("Copy paper", "Printer paper")
    loader = make_loader(tmp_path, invoice_texts={"001": INVOICE_TEXT, "002": duplicate})

    result = run_three_way_check(invoice_path="invoices/001.pdf", loader=loader)
    summary = result.as_dict()

    assert result.requires_human_review is True
    assert result.human_review_reasons == (
        "Invoice number INV-1001 also appears in: 002 (same PO PO-2026-0101).",
    )
    assert summary["first_pass_review"] == "No discrepancy reported."
    assert summary["human_review_reasons"] == list(result.human_review_reasons)
    assert "owner_review_findings" not in summary
    assert "line_link_bases" not in summary


def test_invoice_input_flags_po_receipt_shortfall(tmp_path):
    loader = make_loader(tmp_path, receipt_quantities=["1"])

    result = run_three_way_check(invoice_path="invoices/001.pdf", loader=loader)

    codes = {finding.code for finding in result.findings}
    assert "PO_GR_QTY_MISMATCH" in codes
    assert "QTY_EXCEEDS_RECEIVED" in codes
    assert result.requires_human_review


def test_missing_printed_po_uses_reviewed_link_but_preserves_omission(tmp_path):
    text = INVOICE_TEXT.replace("PO Number:\nPO-2026-0101\n", "")
    loader = make_loader(tmp_path, invoice_texts={"005": text}, no_po_review=True)

    result = run_three_way_check(invoice_path="invoices/005.pdf", loader=loader)

    assert result.purchase_order.po_number == "PO-2026-0101"
    assert {finding.code for finding in result.findings} == {"PO_NOT_PRINTED_ON_INVOICE"}
    assert result.requires_human_review


def test_po_input_runs_when_one_invoice_candidate_exists(tmp_path):
    loader = make_loader(tmp_path)

    result = run_three_way_check(po_number="PO-2026-0101", loader=loader)

    assert result.status == "completed"
    assert result.invoice_case_id == "001"
    assert result.input_type == "po_number"


def test_po_input_requires_invoice_selection_when_multiple_candidates_exist(tmp_path):
    duplicate = INVOICE_TEXT.replace("INV-1001", "INV-1002")
    loader = make_loader(tmp_path, invoice_texts={"001": INVOICE_TEXT, "002": duplicate})

    result = run_three_way_check(po_number="PO-2026-0101", loader=loader)

    assert result.status == "invoice_selection_required"
    assert result.invoice_candidates == ("001", "002")
    assert {finding.code for finding in result.findings} == {"MULTIPLE_INVOICE_CANDIDATES"}
    assert result.human_review_reasons == ("Choose one invoice file before reconciling this PO.",)


@pytest.mark.parametrize("kwargs", [{}, {"invoice_path": "invoices/001.pdf", "po_number": "PO-2026-0101"}])
def test_runner_requires_exactly_one_input_mode(tmp_path, kwargs):
    loader = make_loader(tmp_path)

    with pytest.raises(ValueError, match="exactly one"):
        run_three_way_check(loader=loader, **kwargs)
