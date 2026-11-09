"""Deterministic money parsing and exact invoice/PO/receipt comparisons.

No default tolerance, currency conversion, or silent rounding is applied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence


@dataclass(frozen=True)
class Finding:
    code: str
    message: str


# Parse only source text with an explicit locale; do not route money through float.
def parse_decimal(
    source: str,
    *,
    decimal_separator: str = ".",
    grouping_separator: str | None = None,
) -> Decimal:
    """Parse a source string with explicit separators and preserve its precision."""
    if not isinstance(source, str):
        raise TypeError("Decimal input must be a source string; floats are not accepted")
    if decimal_separator not in {".", ","}:
        raise ValueError("decimal_separator must be '.' or ','")
    if grouping_separator is not None and (len(grouping_separator) != 1 or grouping_separator == decimal_separator):
        raise ValueError("grouping_separator must be one character different from decimal_separator")

    text = source.strip()
    if not text:
        raise ValueError("Decimal source string is empty")
    sign = ""
    if text[0] in "+-":
        sign, text = text[0], text[1:]
    if text.count(decimal_separator) > 1:
        raise ValueError(f"Invalid decimal value: {source!r}")
    integer, separator, fraction = text.partition(decimal_separator)
    if separator and (not fraction or not fraction.isdigit()):
        raise ValueError(f"Invalid decimal value: {source!r}")

    if grouping_separator and grouping_separator in integer:
        group_pattern = rf"\d{{1,3}}(?:{re.escape(grouping_separator)}\d{{3}})+"
        if not re.fullmatch(group_pattern, integer):
            raise ValueError(f"Invalid digit grouping: {source!r}")
        integer = integer.replace(grouping_separator, "")
    elif not integer.isdigit():
        raise ValueError(f"Invalid decimal value: {source!r}")

    normalized = sign + integer + ("." + fraction if separator else "")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal value: {source!r}") from exc


# Compare currency codes directly and require review rather than convert currencies.
def compare_currency(invoice_currency: str, po_currency: str) -> list[Finding]:
    """Flag a currency disagreement without converting either amount."""
    if invoice_currency.strip().upper() != po_currency.strip().upper():
        return [Finding("CURRENCY_MISMATCH", f"Invoice currency {invoice_currency} differs from PO currency {po_currency}.")]
    return []


# Validate line extensions and invoice arithmetic without applying a rounding rule.
def check_invoice_totals(
    invoice: Mapping[str, object],
    *,
    decimal_separator: str = ".",
    grouping_separator: str | None = None,
) -> list[Finding]:
    """Check line extensions and invoice arithmetic using exact Decimal values."""
    findings: list[Finding] = []
    try:
        lines = invoice["line_items"]
        if not isinstance(lines, Sequence) or isinstance(lines, (str, bytes)):
            raise ValueError("line_items must be a sequence")
        line_sum = Decimal("0")
        for index, line in enumerate(lines, start=1):
            if not isinstance(line, Mapping):
                raise ValueError(f"line_items[{index - 1}] must be a mapping")
            quantity = parse_decimal(line["quantity"], decimal_separator=decimal_separator, grouping_separator=grouping_separator)
            price = parse_decimal(line["unit_price"], decimal_separator=decimal_separator, grouping_separator=grouping_separator)
            amount = parse_decimal(line["amount"], decimal_separator=decimal_separator, grouping_separator=grouping_separator)
            expected_amount = quantity * price
            if amount != expected_amount:
                findings.append(Finding("LINE_AMOUNT_MISMATCH", f"Invoice line {index}: quantity × unit price differs from line amount."))
            line_sum += amount

        subtotal = parse_decimal(invoice["subtotal"], decimal_separator=decimal_separator, grouping_separator=grouping_separator)
        discount = parse_decimal(invoice["discount"], decimal_separator=decimal_separator, grouping_separator=grouping_separator)
        tax = parse_decimal(invoice["tax"], decimal_separator=decimal_separator, grouping_separator=grouping_separator)
        total = parse_decimal(invoice["total"], decimal_separator=decimal_separator, grouping_separator=grouping_separator)
        if line_sum != subtotal:
            findings.append(Finding("SUBTOTAL_MISMATCH", "Sum of invoice line amounts differs from subtotal."))
        if subtotal - discount + tax != total:
            findings.append(Finding("TOTAL_MISMATCH", "Subtotal minus discount plus tax differs from invoice total."))
    except (KeyError, TypeError, ValueError) as exc:
        findings.append(Finding("INVALID_OR_MISSING_AMOUNT", str(exc)))
    return findings


# Compare a pre-linked invoice/PO line and any supplied receipt quantities exactly.
def compare_invoice_line(
    invoice_line: Mapping[str, object],
    po_line: Mapping[str, object],
    *,
    receipt_lines: Sequence[Mapping[str, object]] | None = None,
    decimal_separator: str = ".",
    po_decimal_separator: str | None = None,
    receipt_decimal_separator: str | None = None,
    compare_prices: bool = True,
) -> list[Finding]:
    """Compare one already-linked line; `None` means receipt evidence is unchecked."""
    findings: list[Finding] = []
    try:
        invoice_qty = parse_decimal(invoice_line["quantity"], decimal_separator=decimal_separator)
        invoice_price = parse_decimal(invoice_line["unit_price"], decimal_separator=decimal_separator)
        po_format = po_decimal_separator or decimal_separator
        receipt_format = receipt_decimal_separator or decimal_separator
        po_qty = parse_decimal(po_line["quantity"], decimal_separator=po_format)
        po_price = parse_decimal(po_line["unit_price"], decimal_separator=po_format)
        if compare_prices and invoice_price != po_price:
            findings.append(Finding("PRICE_VARIANCE", "Invoice unit price differs from PO unit price."))
        if invoice_qty > po_qty:
            findings.append(Finding("QTY_EXCEEDS_ORDERED", "Invoice quantity exceeds PO quantity."))
        if receipt_lines is not None:
            if not receipt_lines:
                findings.append(Finding("RECEIPT_MISSING", "No receipt lines were supplied for this linked PO line."))
            else:
                received = sum(
                    (parse_decimal(row["quantity"], decimal_separator=receipt_format) for row in receipt_lines),
                    Decimal("0"),
                )
                if received != po_qty:
                    findings.append(Finding("PO_GR_QTY_MISMATCH", "Received quantity differs from PO quantity."))
                if invoice_qty > received:
                    findings.append(Finding("QTY_EXCEEDS_RECEIVED", "Invoice quantity exceeds received quantity."))
    except (KeyError, TypeError, ValueError) as exc:
        findings.append(Finding("INVALID_OR_MISSING_AMOUNT", str(exc)))
    return findings


# Link line items by exact SKU first, then exact normalized description; ambiguity stays unresolved.
def reconcile_invoice(
    invoice: Mapping[str, object],
    purchase_order: Mapping[str, object] | None,
    receipt_records: Sequence[Mapping[str, object]] | None,
    *,
    linked_po_number: str | None = None,
    decimal_separator: str = ".",
    po_decimal_separator: str = ".",
    receipt_decimal_separator: str = ".",
    line_links: Mapping[int, int] | None = None,
) -> list[Finding]:
    """Reconcile a structured invoice candidate against one linked PO and its checked receipts."""
    findings: list[Finding] = []
    invoice_po = invoice.get("po_number")
    po_number = linked_po_number or (invoice_po if isinstance(invoice_po, str) else None)
    if not isinstance(invoice_po, str) or not invoice_po.strip():
        if po_number:
            findings.append(Finding("PO_NOT_PRINTED_ON_INVOICE", "A PO was linked, but the invoice does not state its PO number."))
        else:
            findings.append(Finding("PO_LINK_NOT_PROVIDED", "No invoice PO number or separately reviewed PO link was provided."))
    if purchase_order is None:
        findings.append(Finding("PO_NOT_FOUND", f"No purchase-order record was supplied for {po_number or 'the invoice'}."))
        return findings

    actual_po_number = purchase_order.get("po_number")
    if po_number and actual_po_number != po_number:
        findings.append(Finding("PO_LINK_CONFLICT", "The linked PO number does not match the supplied PO record."))
        return findings
    if isinstance(invoice_po, str) and invoice_po.strip() and actual_po_number != invoice_po:
        findings.append(Finding("PO_LINK_CONFLICT", "The invoice PO number does not match the supplied PO record."))
        return findings

    invoice_currency = invoice.get("currency")
    po_currency = purchase_order.get("currency")
    currency_mismatch = False
    if isinstance(invoice_currency, str) and isinstance(po_currency, str):
        currency_findings = compare_currency(invoice_currency, po_currency)
        findings.extend(currency_findings)
        currency_mismatch = bool(currency_findings)
    findings.extend(check_invoice_totals(invoice, decimal_separator=decimal_separator))

    po_lines = purchase_order.get("lines", [])
    invoice_lines = invoice.get("line_items", [])
    if not isinstance(po_lines, Sequence) or not isinstance(invoice_lines, Sequence):
        findings.append(Finding("LINE_LINK_UNRESOLVED", "Invoice or PO lines are not a readable sequence."))
        return findings
    receipts = receipt_records
    if receipts is None:
        findings.append(Finding("RECEIPTS_NOT_REVIEWED", "Receipt evidence has not been checked."))
    elif not receipts:
        findings.append(Finding("RECEIPT_MISSING", "No receipt records were supplied for the linked PO."))
    elif any(receipt.get("po_number") != actual_po_number for receipt in receipts):
        findings.append(Finding("GR_LINK_CONFLICT", "A supplied receipt does not reference the linked PO."))
        receipts = None

    for invoice_index, invoice_line in enumerate(invoice_lines):
        if not isinstance(invoice_line, Mapping):
            findings.append(Finding("LINE_LINK_UNRESOLVED", "An invoice line is not a readable record."))
            continue
        if line_links is not None and invoice_index in line_links:
            target_line_no = line_links[invoice_index]
            matches = [
                line
                for line in po_lines
                if isinstance(line, Mapping) and line.get("line_no") == target_line_no
            ]
        else:
            matches = _match_purchase_order_line(invoice_line, po_lines)
        if len(matches) > 1:
            findings.append(Finding("LINE_LINK_AMBIGUOUS", "An invoice line matches multiple PO lines."))
            continue
        if not matches:
            code = "LINE_NOT_ON_PO" if invoice_line.get("sku") else "LINE_LINK_UNRESOLVED"
            findings.append(Finding(code, "No unique PO line could be linked to this invoice line."))
            continue
        po_line = matches[0]
        receipt_lines = None
        if receipts is not None and receipts:
            line_no = po_line.get("line_no")
            receipt_lines = [
                line
                for receipt in receipts
                for line in receipt.get("lines", [])
                if line.get("line_no") == line_no
            ]
            if not receipt_lines:
                receipt_lines = [{"quantity": "0"}]
        findings.extend(
            compare_invoice_line(
                invoice_line,
                po_line,
                receipt_lines=receipt_lines,
                decimal_separator=decimal_separator,
                po_decimal_separator=po_decimal_separator,
                receipt_decimal_separator=receipt_decimal_separator,
                compare_prices=not currency_mismatch,
            )
        )
    return findings


def _match_purchase_order_line(
    invoice_line: Mapping[str, object], po_lines: Sequence[object]
) -> list[Mapping[str, object]]:
    sku = invoice_line.get("sku")
    if isinstance(sku, str) and sku.strip():
        return [line for line in po_lines if isinstance(line, Mapping) and line.get("sku") == sku]
    description = invoice_line.get("description")
    if not isinstance(description, str) or not description.strip():
        return []
    normalized = _normalize_description(description)
    return [
        line
        for line in po_lines
        if isinstance(line, Mapping)
        and isinstance(line.get("description"), str)
        and _normalize_description(line["description"]) == normalized
    ]


def _normalize_description(value: str) -> str:
    return re.sub(r"\W+", " ", value.casefold()).strip()
