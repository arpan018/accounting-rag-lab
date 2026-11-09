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
def check_invoice_totals(invoice: Mapping[str, object], *, decimal_separator: str = ".") -> list[Finding]:
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
            quantity = parse_decimal(line["quantity"], decimal_separator=decimal_separator)
            price = parse_decimal(line["unit_price"], decimal_separator=decimal_separator)
            amount = parse_decimal(line["amount"], decimal_separator=decimal_separator)
            expected_amount = quantity * price
            if amount != expected_amount:
                findings.append(Finding("LINE_AMOUNT_MISMATCH", f"Invoice line {index}: quantity × unit price differs from line amount."))
            line_sum += amount

        subtotal = parse_decimal(invoice["subtotal"], decimal_separator=decimal_separator)
        discount = parse_decimal(invoice["discount"], decimal_separator=decimal_separator)
        tax = parse_decimal(invoice["tax"], decimal_separator=decimal_separator)
        total = parse_decimal(invoice["total"], decimal_separator=decimal_separator)
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
) -> list[Finding]:
    """Compare one already-linked line; `None` means receipt evidence is unchecked."""
    findings: list[Finding] = []
    try:
        invoice_qty = parse_decimal(invoice_line["quantity"], decimal_separator=decimal_separator)
        invoice_price = parse_decimal(invoice_line["unit_price"], decimal_separator=decimal_separator)
        po_qty = parse_decimal(po_line["quantity"], decimal_separator=decimal_separator)
        po_price = parse_decimal(po_line["unit_price"], decimal_separator=decimal_separator)
        if invoice_price != po_price:
            findings.append(Finding("PRICE_VARIANCE", "Invoice unit price differs from PO unit price."))
        if invoice_qty > po_qty:
            findings.append(Finding("QTY_EXCEEDS_ORDERED", "Invoice quantity exceeds PO quantity."))
        if receipt_lines is not None:
            if not receipt_lines:
                findings.append(Finding("RECEIPT_MISSING", "No receipt lines were supplied for this linked PO line."))
            else:
                received = sum(
                    (parse_decimal(row["quantity"], decimal_separator=decimal_separator) for row in receipt_lines),
                    Decimal("0"),
                )
                if received != po_qty:
                    findings.append(Finding("PO_GR_QTY_MISMATCH", "Received quantity differs from PO quantity."))
                if invoice_qty > received:
                    findings.append(Finding("QTY_EXCEEDS_RECEIVED", "Invoice quantity exceeds received quantity."))
    except (KeyError, TypeError, ValueError) as exc:
        findings.append(Finding("INVALID_OR_MISSING_AMOUNT", str(exc)))
    return findings
