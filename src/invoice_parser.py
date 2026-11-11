"""Build a structured invoice candidate from selectable PDF text without OCR."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Literal

from src.extraction import ExtractionResult, PageText, extract_pdf
from src.schemas import InvoiceCandidate, InvoiceLineCandidate, SourceLocator


MONEY_TOKEN = re.compile(r"^[\s$€£]*(?:USD|EUR|GBP)?\s*[-+]?[\d.,]+\s*$", re.IGNORECASE)
QUANTITY_TOKEN = re.compile(r"^\d+(?:[.,]\d+)?$")


@dataclass(frozen=True)
class InvoiceParseResult:
    """Keep candidate fields, extraction state, and limitations together."""

    status: Literal["complete", "partial", "unsupported"]
    extraction_status: str
    candidate: InvoiceCandidate
    warnings: tuple[str, ...]


# Read labeled fields from selectable text and preserve the exact source page locator.
def parse_invoice_pdf(path: str, *, source_path: str | None = None) -> InvoiceParseResult:
    extraction = extract_pdf(path)
    if source_path is not None:
        extraction = replace(
            extraction,
            source_path=source_path,
            pages=tuple(replace(page, source_path=source_path) for page in extraction.pages),
        )
    return parse_invoice_extraction(extraction)


# Parse extracted PDF pages into untrusted fields; scanned or incomplete sources stay explicit.
def parse_invoice_extraction(extraction: ExtractionResult) -> InvoiceParseResult:
    pages = [page for page in extraction.pages if page.text.strip()]
    source_page = pages[0] if pages else (extraction.pages[0] if extraction.pages else None)
    source = SourceLocator(
        source_path=extraction.source_path,
        page_number=source_page.page_number if source_page else 1,
    )
    if extraction.status != "selectable_text" or not pages:
        candidate = InvoiceCandidate(source=source)
        return InvoiceParseResult("unsupported", extraction.status, candidate, ("no_selectable_invoice_text",))

    text = "\n".join(page.text for page in pages)
    currency = _detect_currency(text)
    decimal_separator, grouping_separator = _detect_separators(text, currency)
    warnings: list[str] = []
    invoice_number = _labeled_text(text, r"Invoice\s+(?:No\.?|Number|#)")
    po_number = _labeled_text(text, r"PO\s+(?:Number|No\.?|#)")
    vendor = next((line.strip() for line in text.splitlines() if line.strip()), None)
    if not invoice_number:
        warnings.append("invoice_number_not_found")
    if not po_number:
        warnings.append("po_number_not_printed_or_not_found")
    if not currency:
        warnings.append("currency_not_found")

    parsed_lines: list[InvoiceLineCandidate] = []
    line_warnings: list[str] = []
    for page in pages:
        items, page_warnings = _parse_line_items(page)
        parsed_lines.extend(items)
        line_warnings.extend(page_warnings)
    warnings.extend(line_warnings)

    candidate = InvoiceCandidate(
        invoice_number=invoice_number,
        po_number=po_number,
        vendor=vendor,
        currency=currency,
        decimal_separator=decimal_separator,
        grouping_separator=grouping_separator,
        line_items=parsed_lines,
        subtotal=_labeled_amount(text, r"Subtotal"),
        discount=_labeled_amount(text, r"Discount"),
        tax=_labeled_amount(text, r"(?:Sales\s+)?Tax(?:\s*\([^\n]*\))?"),
        total=_labeled_amount(text, r"Total\s+Due"),
        source=source,
    )
    if candidate.subtotal is None:
        warnings.append("subtotal_not_found")
    if candidate.tax is None:
        warnings.append("tax_not_found")
    if candidate.total is None:
        warnings.append("total_not_found")
    if not candidate.line_items:
        warnings.append("invoice_lines_not_parsed")

    required_found = bool(
        candidate.invoice_number
        and candidate.currency
        and candidate.line_items
        and candidate.subtotal
        and candidate.tax
        and candidate.total
    )
    status: Literal["complete", "partial", "unsupported"] = "complete" if required_found and not line_warnings else "partial"
    return InvoiceParseResult(status, extraction.status, candidate, tuple(dict.fromkeys(warnings)))


# Match a label and read its value either beside the label or on the next non-empty line.
def _labeled_text(text: str, label_pattern: str) -> str | None:
    lines = text.splitlines()
    label = re.compile(rf"^\s*{label_pattern}\s*:?\s*(.*?)\s*$", re.IGNORECASE)
    for index, line in enumerate(lines):
        match = label.match(line)
        if not match:
            continue
        if match.group(1):
            return match.group(1).strip()
        for value in lines[index + 1 :]:
            if value.strip():
                return value.strip()
    return None


# Read a labeled currency amount and remove symbols while preserving its digit separators.
def _labeled_amount(text: str, label_pattern: str) -> str | None:
    value = _labeled_text(text, label_pattern)
    if value is None or not MONEY_TOKEN.fullmatch(value):
        return None
    return _amount_digits(value)


# Extract table rows using the repeated description, quantity, price, and amount pattern.
def _parse_line_items(page: PageText) -> tuple[list[InvoiceLineCandidate], list[str]]:
    lines = page.text.splitlines()
    header = next((index for index, line in enumerate(lines) if line.strip().casefold() == "description"), None)
    if header is None:
        return [], [f"line_table_not_found_page_{page.page_number}"]
    amount_header = next(
        (index for index in range(header + 1, len(lines)) if lines[index].strip().casefold() == "amount"),
        None,
    )
    if amount_header is None:
        return [], [f"line_amount_column_not_found_page_{page.page_number}"]

    items: list[InvoiceLineCandidate] = []
    warnings: list[str] = []
    description_parts: list[str] = []
    index = amount_header + 1
    while index < len(lines) and not re.match(r"^\s*Subtotal\b", lines[index], re.IGNORECASE):
        value = lines[index].strip()
        if QUANTITY_TOKEN.fullmatch(value):
            description = " ".join(description_parts).strip()
            price = lines[index + 1].strip() if index + 1 < len(lines) else ""
            amount = lines[index + 2].strip() if index + 2 < len(lines) else ""
            if not description or not MONEY_TOKEN.fullmatch(price) or not MONEY_TOKEN.fullmatch(amount):
                warnings.append(f"line_{len(items) + 1}_incomplete_page_{page.page_number}")
                description_parts.clear()
                index += 1
                continue
            items.append(
                InvoiceLineCandidate(
                    description=description,
                    quantity=value,
                    unit_price=_amount_digits(price),
                    amount=_amount_digits(amount),
                    source=SourceLocator(source_path=page.source_path, page_number=page.page_number),
                )
            )
            description_parts.clear()
            index += 3
            continue
        if value and value.casefold() not in {"qty", "unit price"}:
            description_parts.append(value)
        index += 1
    if description_parts:
        warnings.append(f"unmatched_description_text_page_{page.page_number}")
    return items, warnings


# Identify a currency symbol/code from the source text without converting amounts.
def _detect_currency(text: str) -> str | None:
    if "$" in text or re.search(r"\bUSD\b", text, re.IGNORECASE):
        return "USD"
    if "€" in text or re.search(r"\bEUR\b", text, re.IGNORECASE):
        return "EUR"
    if "£" in text or re.search(r"\bGBP\b", text, re.IGNORECASE):
        return "GBP"
    return None


# Choose explicit source separators from currency and observed amount punctuation.
def _detect_separators(text: str, currency: str | None) -> tuple[str, str | None]:
    amounts = re.findall(r"(?<!\w)[€£$]?\s*\d[\d.,]*\d(?!\w)", text)
    has_comma_decimal = any(re.search(r",\d{1,2}$", token.strip()) for token in amounts)
    has_dot_decimal = any(re.search(r"\.\d{1,2}$", token.strip()) for token in amounts)
    if has_comma_decimal and not has_dot_decimal and currency in {"EUR", "GBP"}:
        return ",", "."
    return ".", ","


# Strip currency markers but leave the original decimal/grouping punctuation unchanged.
def _amount_digits(value: str) -> str:
    return re.sub(r"(?i)USD|EUR|GBP|[$€£\s]", "", value)
