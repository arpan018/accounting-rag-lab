"""T12b tests: allowlisted invoice loading and exact PO, receipt, and reviewed-link resolution."""

import csv
import json

import pymupdf
import pytest

from src.record_loader import SourceRecordLoader


def make_pdf(path, text: str) -> None:
    """Write a small selectable-text invoice fixture."""
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def make_loader(
    tmp_path,
    *,
    invoices,
    purchase_orders=None,
    receipts=None,
    review_rows=None,
    working_po_candidates=None,
):
    """Create isolated raw files plus allowlist and review CSV fixtures."""
    raw_root = tmp_path / "raw"
    (raw_root / "invoices").mkdir(parents=True)
    for case_id, text in invoices.items():
        make_pdf(raw_root / "invoices" / f"{case_id}.pdf", text)
    (raw_root / "purchase_orders.json").write_text(
        json.dumps(purchase_orders or []), encoding="utf-8"
    )
    (raw_root / "receipts.json").write_text(json.dumps(receipts or []), encoding="utf-8")

    working_path = tmp_path / "working_set.csv"
    working_fields = ["case_id", "invoice_source", "po_record_reference", "receipt_record_reference"]
    with working_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=working_fields)
        writer.writeheader()
        for case_id in invoices:
            default_po = (purchase_orders or [{}])[0].get("po_number", "")
            po_number = (working_po_candidates or {}).get(case_id, default_po)
            writer.writerow(
                {
                    "case_id": case_id,
                    "invoice_source": f"invoices/{case_id}.pdf",
                    "po_record_reference": f"purchase_orders.json#{po_number}" if po_number else "",
                    "receipt_record_reference": "",
                }
            )

    review_path = tmp_path / "review_queue.csv"
    review_fields = [
        "case_id",
        "owner_verified_po_gr_links",
        "owner_verified_expected_findings",
        "review_status",
    ]
    reviews = review_rows or [
        {"case_id": case_id, "owner_verified_po_gr_links": "", "review_status": "reviewed"}
        for case_id in invoices
    ]
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=review_fields)
        writer.writeheader()
        writer.writerows(reviews)
    return SourceRecordLoader(raw_root, working_path, review_path), raw_root


def po_record(po_number="PO-2026-0101", *, receipt_required=True):
    """Return a source-shaped PO fixture with string money and quantity values."""
    return {
        "po_number": po_number,
        "vendor": "Example Vendor",
        "currency": "USD",
        "receipt_required": receipt_required,
        "lines": [{"line_no": 1, "sku": "ITEM-1", "description": "Item", "quantity": "2", "unit_price": "12.50"}],
    }


def receipt_record(receipt_id, po_number="PO-2026-0101"):
    """Return a source-shaped GR fixture linked by the shared PO number."""
    return {
        "receipt_id": receipt_id,
        "po_number": po_number,
        "date": "2026-03-02",
        "lines": [{"line_no": 1, "quantity": "2"}],
    }


def test_po_input_returns_every_receipt_and_multiple_exact_invoice_candidates(tmp_path):
    loader, _ = make_loader(
        tmp_path,
        invoices={
            "001": "Invoice No: INV-001 PO Number: PO-2026-0101",
            "005": "Invoice No: INV-005 no PO printed",
        },
        purchase_orders=[po_record()],
        receipts=[receipt_record("GR-00001"), receipt_record("GR-00002")],
        review_rows=[
            {"case_id": "001", "owner_verified_po_gr_links": "", "review_status": "reviewed"},
            {"case_id": "005", "owner_verified_po_gr_links": "PO and receipt match; corresponding record PO-2026-0101", "review_status": "reviewed"},
        ],
    )

    result = loader.resolve_po_number("PO-2026-0101")

    assert result.status == "found"
    assert result.purchase_order.po_number == "PO-2026-0101"
    assert {receipt.receipt_id for receipt in result.receipt_records} == {"GR-00001", "GR-00002"}
    assert result.receipt_status == "available"
    assert {case.case_id for case in result.invoice_candidates} == {"001", "005"}


def test_invoice_input_uses_exact_printed_po_and_resolves_all_receipts(tmp_path):
    loader, raw_root = make_loader(
        tmp_path,
        invoices={"001": "Invoice No: INV-001\nPO Number: PO-2026-0101"},
        purchase_orders=[po_record()],
        receipts=[receipt_record("GR-00001"), receipt_record("GR-00002")],
    )

    result = loader.resolve_invoice_path(raw_root / "invoices" / "001.pdf")

    assert result.printed_po_numbers == ("PO-2026-0101",)
    assert result.link_status == "linked"
    assert result.purchase_order.po_number == "PO-2026-0101"
    assert len(result.receipt_records) == 2


def test_invoice_without_printed_po_uses_only_explicit_reviewed_link(tmp_path):
    loader, _ = make_loader(
        tmp_path,
        invoices={"005": "Invoice No: INV-005\nNo purchase order printed"},
        purchase_orders=[po_record()],
        receipts=[receipt_record("GR-00001")],
        review_rows=[
            {"case_id": "005", "owner_verified_po_gr_links": "Owner identifies PO-2026-0101 as corresponding record; PO and receipt match.", "review_status": "reviewed"}
        ],
    )

    result = loader.resolve_invoice_path("invoices/005.pdf")

    assert result.printed_po_numbers == ()
    assert result.owner_review_po_candidates == ("PO-2026-0101",)
    assert result.linked_po_number == "PO-2026-0101"
    assert result.link_status == "linked"
    assert result.purchase_order is not None
    assert result.receipt_records[0].receipt_id == "GR-00001"


def test_unreviewed_working_set_po_pointer_is_not_promoted_to_a_link(tmp_path):
    loader, _ = make_loader(
        tmp_path,
        invoices={"005": "Invoice No: INV-005\nNo purchase order printed"},
        purchase_orders=[po_record()],
        review_rows=[
            {"case_id": "005", "owner_verified_po_gr_links": "PO-2026-0101", "review_status": "not_reviewed"}
        ],
    )

    result = loader.resolve_invoice_path("invoices/005.pdf")

    assert result.linked_po_number is None
    assert result.link_status == "unreviewed"
    assert result.purchase_order is None
    assert result.receipt_status == "unknown"


def test_disagreeing_printed_and_working_set_po_candidates_are_conflicting(tmp_path):
    loader, _ = make_loader(
        tmp_path,
        invoices={"001": "Invoice No: INV-001\nPO Number: PO-2026-0101"},
        purchase_orders=[po_record("PO-2026-0101"), po_record("PO-2026-0102")],
        working_po_candidates={"001": "PO-2026-0102"},
    )

    result = loader.resolve_invoice_path("invoices/001.pdf")

    assert result.link_status == "conflicting"
    assert result.linked_po_number is None
    assert result.purchase_order is None


def test_invoice_without_printed_or_reviewed_po_is_missing_link(tmp_path):
    loader, _ = make_loader(
        tmp_path,
        invoices={"001": "Invoice No: INV-001\nNo purchase order printed"},
        purchase_orders=[po_record()],
        review_rows=[
            {"case_id": "001", "owner_verified_po_gr_links": "", "review_status": "reviewed"}
        ],
        working_po_candidates={"001": ""},
    )

    result = loader.resolve_invoice_path("invoices/001.pdf")

    assert result.link_status == "missing"
    assert result.linked_po_number is None
    assert result.purchase_order is None
    assert result.receipt_status == "unknown"


def test_first_pass_review_remains_visible_for_uncertain_po_candidates(tmp_path):
    loader, _ = make_loader(
        tmp_path,
        invoices={"008": "Invoice No: INV-008\nPO Number: PO-2026-0101"},
        purchase_orders=[po_record()],
        review_rows=[
            {
                "case_id": "008",
                "owner_verified_po_gr_links": "PO-2026-0101 appears to be a different vendor; link uncertain.",
                "owner_verified_expected_findings": "Possible vendor/PO mismatch; unresolved.",
                "review_status": "reviewed",
            }
        ],
    )

    result = loader.resolve_invoice_path("invoices/008.pdf")

    assert result.link_status == "linked"
    assert "unresolved" in result.first_pass_review


def test_missing_po_and_receipt_states_are_explicit(tmp_path):
    loader, _ = make_loader(
        tmp_path,
        invoices={"001": "Invoice No: INV-001 PO Number: PO-2026-0101"},
        purchase_orders=[po_record()],
    )

    missing = loader.resolve_po_number("PO-2026-0999")
    no_receipt = loader.resolve_po_number("PO-2026-0101")

    assert missing.status == "not_found"
    assert missing.receipt_status == "unknown"
    assert no_receipt.status == "found"
    assert no_receipt.receipt_status == "missing"
    assert no_receipt.receipt_records == ()


def test_receipt_status_is_not_required_when_po_says_no_receipt_needed(tmp_path):
    loader, _ = make_loader(
        tmp_path,
        invoices={},
        purchase_orders=[po_record(receipt_required=False)],
    )

    result = loader.resolve_po_number("PO-2026-0101")

    assert result.receipt_status == "not_required"


@pytest.mark.parametrize("duplicate_file", ["purchase_orders.json", "receipts.json"])
def test_duplicate_source_record_ids_are_rejected(tmp_path, duplicate_file):
    kwargs = {
        "invoices": {},
        "purchase_orders": [po_record(), po_record()],
        "receipts": [receipt_record("GR-00001"), receipt_record("GR-00001")],
    }
    if duplicate_file == "purchase_orders.json":
        kwargs["receipts"] = []
    else:
        kwargs["purchase_orders"] = [po_record()]

    with pytest.raises(ValueError, match="duplicate"):
        make_loader(tmp_path, **kwargs)


def test_invoice_path_must_be_in_working_set_and_po_input_must_be_exact(tmp_path):
    loader, _ = make_loader(tmp_path, invoices={"001": "Invoice No: INV-001"})

    with pytest.raises(ValueError, match="not present in eval/working_set.csv"):
        loader.resolve_invoice_path("invoices/outside.pdf")
    with pytest.raises(ValueError, match="PO-YYYY-NNNN"):
        loader.resolve_po_number("po-2026-0101")
