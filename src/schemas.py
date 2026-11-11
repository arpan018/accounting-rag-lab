"""Strict Pydantic schemas for invoice candidates and purchasing evidence."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

from src.reconciliation import parse_decimal


class StrictSourceModel(BaseModel):
    """Reject unrecognized keys and implicit type coercion in source records."""

    model_config = ConfigDict(extra="forbid", strict=True)


class SourceLocator(StrictSourceModel):
    """Identify a source page or a stable JSON record."""

    source_path: StrictStr
    page_number: StrictInt | None = Field(default=None, gt=0)
    record_id: StrictStr | None = None

    # A source locator must resolve to one precise page or record, never both.
    @model_validator(mode="after")
    def require_one_location(self) -> SourceLocator:
        if not self.source_path.strip():
            raise ValueError("source_path must not be empty")
        if (self.page_number is None) == (self.record_id is None):
            raise ValueError("provide exactly one of page_number or record_id")
        if self.record_id is not None and not self.record_id.strip():
            raise ValueError("record_id must not be empty")
        return self


class LocaleAwareModel(StrictSourceModel):
    """Keep numeric source strings intact while recording their separators."""

    decimal_separator: Literal[".", ","] = "."
    grouping_separator: Literal[".", ","] | None = None

    # Convert source strings with the existing strict Decimal parser on demand.
    def decimal_value(self, source_text: str) -> Decimal:
        return parse_decimal(
            source_text,
            decimal_separator=self.decimal_separator,
            grouping_separator=self.grouping_separator,
        )

    # Reject malformed localized numeric strings during model validation.
    def _check_decimal_fields(self, *field_names: str) -> None:
        if self.grouping_separator == self.decimal_separator:
            raise ValueError("grouping_separator must differ from decimal_separator")
        for field_name in field_names:
            source_text = getattr(self, field_name)
            if source_text is not None:
                self.decimal_value(source_text)


class InvoiceLineCandidate(LocaleAwareModel):
    """Represent extracted invoice line values without losing source strings."""

    sku: StrictStr | None = None
    description: StrictStr | None = None
    quantity: StrictStr | None = None
    unit_price: StrictStr | None = None
    amount: StrictStr | None = None
    source: SourceLocator

    # Require a usable matching label while allowing incomplete extraction candidates.
    @model_validator(mode="after")
    def validate_line(self) -> InvoiceLineCandidate:
        if not any(value and value.strip() for value in (self.sku, self.description)):
            raise ValueError("invoice line requires a non-empty SKU or description")
        self._check_decimal_fields("quantity", "unit_price", "amount")
        return self


class InvoiceCandidate(LocaleAwareModel):
    """Hold untrusted invoice fields with the page that supports the candidate."""

    invoice_number: StrictStr | None = None
    po_number: StrictStr | None = None
    vendor: StrictStr | None = None
    currency: StrictStr | None = None
    line_items: list[InvoiceLineCandidate] = Field(default_factory=list)
    subtotal: StrictStr | None = None
    discount: StrictStr | None = None
    tax: StrictStr | None = None
    total: StrictStr | None = None
    source: SourceLocator

    # Validate every available total with the invoice's explicit locale settings.
    @model_validator(mode="after")
    def validate_totals(self) -> InvoiceCandidate:
        self._check_decimal_fields("subtotal", "discount", "tax", "total")
        if self.po_number is not None and not self.po_number.strip():
            raise ValueError("po_number must be non-empty or None")
        return self


class PurchaseOrderLine(StrictSourceModel):
    """Validate a source PO line using its original numeric strings."""

    line_no: StrictInt = Field(ge=1)
    sku: StrictStr | None = None
    description: StrictStr | None = None
    quantity: StrictStr
    unit_price: StrictStr

    # Require a line label and valid quantity and unit-price source strings.
    @model_validator(mode="after")
    def validate_line(self) -> PurchaseOrderLine:
        if not any(value and value.strip() for value in (self.sku, self.description)):
            raise ValueError("PO line requires a non-empty SKU or description")
        parse_decimal(self.quantity, decimal_separator=".")
        parse_decimal(self.unit_price, decimal_separator=".")
        return self


class PurchaseOrderRecord(StrictSourceModel):
    """Represent one source PO record and its provenance."""

    po_number: StrictStr
    vendor: StrictStr
    currency: StrictStr
    receipt_required: StrictBool
    lines: list[PurchaseOrderLine] = Field(min_length=1)
    source: SourceLocator

    # Prevent empty IDs and duplicate line numbers from entering reconciliation.
    @model_validator(mode="after")
    def validate_record(self) -> PurchaseOrderRecord:
        if not self.po_number.strip() or not self.vendor.strip() or not self.currency.strip():
            raise ValueError("PO number, vendor, and currency must be non-empty")
        line_numbers = [line.line_no for line in self.lines]
        if len(line_numbers) != len(set(line_numbers)):
            raise ValueError("PO line numbers must be unique")
        return self


class GoodsReceiptLine(LocaleAwareModel):
    """Validate one received quantity without converting it through float."""

    line_no: StrictInt = Field(ge=1)
    quantity: StrictStr

    # Parse the received quantity using the source record's declared separators.
    @model_validator(mode="after")
    def validate_quantity(self) -> GoodsReceiptLine:
        self._check_decimal_fields("quantity")
        return self


class GoodsReceiptRecord(LocaleAwareModel):
    """Represent one receipt and its exact PO link."""

    receipt_id: StrictStr
    po_number: StrictStr
    date: StrictStr
    lines: list[GoodsReceiptLine] = Field(default_factory=list)
    source: SourceLocator

    # Keep receipt and PO identifiers explicit and reject duplicate receipt lines.
    @model_validator(mode="after")
    def validate_record(self) -> GoodsReceiptRecord:
        if not self.receipt_id.strip() or not self.po_number.strip() or not self.date.strip():
            raise ValueError("receipt ID, PO number, and date must be non-empty")
        line_numbers = [line.line_no for line in self.lines]
        if len(line_numbers) != len(set(line_numbers)):
            raise ValueError("receipt line numbers must be unique")
        return self
