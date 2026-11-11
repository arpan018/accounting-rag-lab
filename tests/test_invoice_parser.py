"""T12c tests: parse selectable invoice PDFs into source-cited Pydantic candidates; no OCR."""

from decimal import Decimal

import pymupdf

from src.invoice_parser import parse_invoice_pdf


def make_pdf(path, text: str) -> None:
    """Create a fixture PDF with selectable text."""
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def test_parses_invoice_fields_lines_and_page_provenance(tmp_path):
    path = tmp_path / "invoice.pdf"
    make_pdf(
        path,
        """Example Vendor
INVOICE
Invoice No:
INV-1001
PO Number:
PO-2026-0101
Description
Qty
Unit Price
Amount
Paper A4
20
$6.49
$129.80
Subtotal
$129.80
Sales Tax (0%)
$0.00
Total Due
$129.80
""",
    )

    result = parse_invoice_pdf(str(path))

    assert result.status == "complete"
    assert result.candidate.invoice_number == "INV-1001"
    assert result.candidate.po_number == "PO-2026-0101"
    assert result.candidate.currency == "USD"
    assert result.candidate.line_items[0].quantity == "20"
    assert result.candidate.line_items[0].unit_price == "6.49"
    assert result.candidate.line_items[0].amount == "129.80"
    assert result.candidate.line_items[0].source.page_number == 1
    assert result.candidate.source.source_path == path.as_posix()
    assert result.candidate.decimal_value(result.candidate.total) == Decimal("129.80")


def test_keeps_missing_printed_po_explicit_and_joins_wrapped_descriptions(tmp_path):
    path = tmp_path / "invoice-no-po.pdf"
    make_pdf(
        path,
        """Example Vendor
Invoice No: INV-1002
Description
Qty
Unit Price
Amount
Premium copy paper
ream of 500
2
$12.50
$25.00
Subtotal
$25.00
Tax
$0.00
Total Due
$25.00
""",
    )

    result = parse_invoice_pdf(str(path))

    assert result.status == "complete"
    assert result.candidate.po_number is None
    assert result.candidate.line_items[0].description == "Premium copy paper ream of 500"
    assert "po_number_not_printed_or_not_found" in result.warnings


def test_scanned_or_empty_text_pdf_is_unsupported_without_ocr(tmp_path):
    path = tmp_path / "scan.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(path)
    document.close()

    result = parse_invoice_pdf(str(path))

    assert result.status == "unsupported"
    assert result.extraction_status == "no_text_layer"
    assert result.candidate.invoice_number is None
    assert result.warnings == ("no_selectable_invoice_text",)
