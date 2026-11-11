"""T12a tests: strict Pydantic invoice, PO, GR, and source-location schemas."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.schemas import (
    GoodsReceiptRecord,
    InvoiceCandidate,
    PurchaseOrderRecord,
    SourceLocator,
)


def invoice_source(page: int = 1) -> dict[str, object]:
    return {"source_path": "invoices/sample.pdf", "page_number": page}


def record_source(record_id: str, path: str = "purchase_orders.json") -> dict[str, object]:
    return {"source_path": path, "record_id": record_id}


def test_source_shaped_po_and_receipt_records_validate_with_attached_provenance():
    po_data = {
        "po_number": "PO-2026-0101",
        "vendor": "Example Vendor",
        "currency": "USD",
        "receipt_required": True,
        "lines": [{"line_no": 1, "sku": "ITEM-1", "description": "Example item", "quantity": "2", "unit_price": "12.50"}],
        "source": record_source("PO-2026-0101"),
    }
    receipt_data = {
        "receipt_id": "GR-00001",
        "po_number": "PO-2026-0101",
        "date": "2026-03-02",
        "lines": [{"line_no": 1, "quantity": "2"}],
        "source": record_source("GR-00001", "receipts.json"),
    }

    po = PurchaseOrderRecord.model_validate(po_data)
    receipt = GoodsReceiptRecord.model_validate(receipt_data)

    assert po.lines[0].unit_price == "12.50"
    assert po.source.record_id == "PO-2026-0101"
    assert receipt.lines[0].quantity == "2"
    assert receipt.source.record_id == "GR-00001"


def test_invoice_candidate_preserves_comma_decimal_and_exposes_decimal_value():
    candidate = InvoiceCandidate.model_validate(
        {
            "invoice_number": "EU-1001",
            "po_number": None,
            "currency": "EUR",
            "decimal_separator": ",",
            "line_items": [
                {
                    "sku": "SKU-1",
                    "quantity": "2",
                    "unit_price": "12,5",
                    "amount": "25,0",
                    "decimal_separator": ",",
                    "source": invoice_source(),
                }
            ],
            "total": "25,0",
            "source": invoice_source(),
        }
    )

    line = candidate.line_items[0]
    assert line.unit_price == "12,5"
    assert line.decimal_value(line.unit_price) == Decimal("12.5")
    assert candidate.decimal_value(candidate.total) == Decimal("25")


@pytest.mark.parametrize(
    ("model", "data"),
    [
        (
            InvoiceCandidate,
            {"line_items": [{"description": "item", "unit_price": 12.5, "source": invoice_source()}], "source": invoice_source()},
        ),
        (
            PurchaseOrderRecord,
            {"po_number": "P1", "vendor": "Vendor", "currency": "USD", "receipt_required": True, "lines": [{"line_no": 1, "sku": "S1", "quantity": "1", "unit_price": 12.5}], "source": record_source("P1")},
        ),
        (
            GoodsReceiptRecord,
            {"receipt_id": "G1", "po_number": "P1", "date": "2026-01-01", "lines": [{"line_no": 1, "quantity": 1.0}], "source": record_source("G1", "receipts.json")},
        ),
    ],
)
def test_schema_rejects_float_numeric_values(model, data):
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_invoice_candidate_rejects_malformed_decimal_and_preserves_negative_text():
    with pytest.raises(ValidationError):
        InvoiceCandidate.model_validate(
            {
                "line_items": [{"description": "item", "unit_price": "12,5", "source": invoice_source()}],
                "source": invoice_source(),
            }
        )

    candidate = InvoiceCandidate.model_validate(
        {
            "line_items": [{"description": "credit", "amount": "-1.25", "source": invoice_source()}],
            "source": invoice_source(),
        }
    )
    assert candidate.line_items[0].amount == "-1.25"
    assert candidate.line_items[0].decimal_value(candidate.line_items[0].amount) == Decimal("-1.25")


def test_po_requires_unique_lines_and_explicit_identifiers():
    base = {
        "po_number": "PO-1",
        "vendor": "Vendor",
        "currency": "USD",
        "receipt_required": True,
        "lines": [
            {"line_no": 1, "sku": "S1", "quantity": "1", "unit_price": "2.00"},
            {"line_no": 1, "sku": "S2", "quantity": "1", "unit_price": "3.00"},
        ],
        "source": record_source("PO-1"),
    }
    with pytest.raises(ValidationError, match="line numbers must be unique"):
        PurchaseOrderRecord.model_validate(base)

    base["po_number"] = ""
    with pytest.raises(ValidationError, match="must be non-empty"):
        PurchaseOrderRecord.model_validate(base)


def test_source_locator_requires_exactly_one_page_or_record_id():
    with pytest.raises(ValidationError, match="exactly one"):
        SourceLocator(source_path="invoices/a.pdf")
    with pytest.raises(ValidationError, match="exactly one"):
        SourceLocator(source_path="invoices/a.pdf", page_number=1, record_id="A")
    assert SourceLocator(source_path="invoices/a.pdf", page_number=1).page_number == 1
    assert SourceLocator(source_path="purchase_orders.json", record_id="PO-1").record_id == "PO-1"


def test_schemas_reject_unknown_fields_to_catch_source_shape_drift():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PurchaseOrderRecord.model_validate(
            {
                "po_number": "P1",
                "vendor": "Vendor",
                "currency": "USD",
                "receipt_required": True,
                "lines": [{"line_no": 1, "sku": "S1", "quantity": "1", "unit_price": "2.00"}],
                "source": record_source("P1"),
                "unexpected": "value",
            }
        )
