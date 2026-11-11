"""Run one invoice-to-PO-to-receipt check with explicit evidence and review findings."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Literal, Mapping

from src.invoice_parser import InvoiceParseResult, parse_invoice_pdf
from src.reconciliation import Finding, parse_decimal, reconcile_invoice
from src.record_loader import InvoiceLinkResolution, SourceRecordLoader
from src.schemas import (
    GoodsReceiptRecord,
    InvoiceCandidate,
    InvoiceLineCandidate,
    PurchaseOrderLine,
    PurchaseOrderRecord,
)


@dataclass(frozen=True)
class LineLink:
    """Expose how one invoice line maps to the selected PO line and SKU."""

    invoice_line_no: int
    invoice_description: str | None
    invoice_sku: str | None
    po_line_no: int
    po_description: str | None
    po_sku: str | None
    basis: str


@dataclass(frozen=True)
class ThreeWayResult:
    """Summarize one processing run without treating findings as approvals."""

    status: Literal[
        "completed",
        "po_not_found",
        "invoice_not_found",
        "invoice_selection_required",
        "invoice_link_unresolved",
        "invoice_extraction_unsupported",
    ]
    input_type: Literal["invoice_path", "po_number"]
    input_value: str
    invoice_case_id: str | None
    invoice_candidates: tuple[str, ...]
    candidate: InvoiceCandidate | None
    purchase_order: PurchaseOrderRecord | None
    receipt_records: tuple[GoodsReceiptRecord, ...]
    findings: tuple[Finding, ...]
    citations: tuple[str, ...]
    extraction_warnings: tuple[str, ...]
    calculation_notes: tuple[str, ...]
    line_links: tuple[LineLink, ...]
    first_pass_review: str
    human_review_reasons: tuple[str, ...]
    requires_human_review: bool

    # Export a source-safe summary suitable for terminal display and review notes.
    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "input": {"type": self.input_type, "value": self.input_value},
            "invoice_case_id": self.invoice_case_id,
            "invoice_candidates": list(self.invoice_candidates),
            "invoice": _invoice_summary(self.candidate) if self.candidate else None,
            "purchase_order": _po_summary(self.purchase_order) if self.purchase_order else None,
            "receipts": [_receipt_summary(record) for record in self.receipt_records],
            "findings": [{"code": item.code, "message": item.message} for item in self.findings],
            "citations": list(self.citations),
            "extraction_warnings": list(self.extraction_warnings),
            "calculation_notes": list(self.calculation_notes),
            "line_match_summary": {
                "invoice_lines": len(self.candidate.line_items) if self.candidate else 0,
                "linked_to_po": len(self.line_links),
                "unresolved": max(
                    0,
                    (len(self.candidate.line_items) if self.candidate else 0) - len(self.line_links),
                ),
            },
            "first_pass_review": self.first_pass_review,
            "human_review_reasons": list(self.human_review_reasons),
            "requires_human_review": self.requires_human_review,
        }


# Accept exactly one input mode, then resolve documents before deterministic comparison.
def run_three_way_check(
    *,
    invoice_path: str | Path | None = None,
    po_number: str | None = None,
    loader: SourceRecordLoader | None = None,
    line_links: Mapping[int, int] | None = None,
    line_links_verified: bool = False,
) -> ThreeWayResult:
    if (invoice_path is None) == (po_number is None):
        raise ValueError("provide exactly one of invoice_path or po_number")
    source_loader = loader or SourceRecordLoader()
    if invoice_path is not None:
        resolution = source_loader.resolve_invoice_path(invoice_path)
        return _run_invoice_resolution(
            source_loader,
            resolution,
            input_type="invoice_path",
            input_value=str(invoice_path),
            line_links=line_links,
            line_links_verified=line_links_verified,
        )

    assert po_number is not None
    po_result = source_loader.resolve_po_number(po_number)
    citations = _record_citations(po_result.purchase_order, po_result.receipt_records)
    if po_result.status == "not_found":
        return _empty_result(
            "po_not_found", "po_number", po_number,
            (Finding("PO_NOT_FOUND", f"No purchase-order record exists for {po_number}."),), citations,
        )
    cases = tuple(item.case_id for item in po_result.invoice_candidates)
    if not cases:
        return _empty_result(
            "invoice_not_found", "po_number", po_number,
            (Finding("INVOICE_NOT_FOUND", "No working-set invoice has this printed or owner-reviewed PO candidate."),),
            citations,
            purchase_order=po_result.purchase_order,
            receipt_records=po_result.receipt_records,
        )
    if len(cases) > 1:
        return ThreeWayResult(
            status="invoice_selection_required",
            input_type="po_number",
            input_value=po_number,
            invoice_case_id=None,
            invoice_candidates=cases,
            candidate=None,
            purchase_order=po_result.purchase_order,
            receipt_records=po_result.receipt_records,
            findings=(Finding("MULTIPLE_INVOICE_CANDIDATES", "Choose one invoice file before reconciling this PO."),),
            citations=citations,
            extraction_warnings=(),
            calculation_notes=(),
            line_links=(),
            first_pass_review="",
            human_review_reasons=("Choose one invoice file before reconciling this PO.",),
            requires_human_review=True,
        )
    resolution = po_result.invoice_candidates[0]
    return _run_invoice_resolution(
        source_loader,
        resolution,
        input_type="po_number",
        input_value=po_number,
        line_links=line_links,
        line_links_verified=line_links_verified,
    )


# Run extraction, exact link checks, candidate line linking, and Decimal reconciliation for one invoice.
def _run_invoice_resolution(
    loader: SourceRecordLoader,
    resolution: InvoiceLinkResolution,
    *,
    input_type: Literal["invoice_path", "po_number"],
    input_value: str,
    line_links: Mapping[int, int] | None,
    line_links_verified: bool,
) -> ThreeWayResult:
    absolute_path = loader.raw_root / resolution.invoice_source
    display_path = _display_path(absolute_path)
    parsed = parse_invoice_pdf(str(absolute_path), source_path=display_path)
    citations = _candidate_citations(parsed.candidate, resolution)
    findings: list[Finding] = []

    if parsed.status == "unsupported":
        findings.append(Finding("INVOICE_EXTRACTION_UNSUPPORTED", "Invoice text is unavailable; OCR is outside this v1 flow."))
        return _result_from_resolution(
            "invoice_extraction_unsupported", input_type, input_value, resolution, parsed,
            findings, citations, (),
        )

    if resolution.link_status != "linked" or resolution.purchase_order is None:
        status, code, message = _link_failure(resolution)
        findings.append(Finding(code, message))
        return _result_from_resolution(status, input_type, input_value, resolution, parsed, findings, citations, ())

    candidate = parsed.candidate
    purchase_order = resolution.purchase_order
    if candidate.vendor and _normalize_vendor(candidate.vendor) != _normalize_vendor(purchase_order.vendor):
        findings.append(Finding("VENDOR_MISMATCH", "Invoice vendor text differs from the linked PO vendor; confirm this link."))

    proposed_links, line_links, link_findings = _propose_line_links(
        candidate,
        purchase_order,
        explicit_links=line_links,
        explicit_links_verified=line_links_verified,
    )
    findings.extend(link_findings)
    invoice_data = _reconciliation_invoice(candidate)
    calculation_notes: list[str] = []
    if candidate.discount is None:
        calculation_notes.append("Invoice does not state a discount; arithmetic check assumes zero discount.")
    po_data = purchase_order.model_dump(exclude={"source"})
    receipt_data = [record.model_dump(exclude={"source"}) for record in resolution.receipt_records]
    findings.extend(
        reconcile_invoice(
            invoice_data,
            po_data,
            receipt_data,
            linked_po_number=resolution.linked_po_number,
            decimal_separator=candidate.decimal_separator,
            po_decimal_separator=".",
            receipt_decimal_separator=".",
            line_links=proposed_links,
        )
    )
    findings.extend(_duplicate_invoice_findings(
        loader, candidate, resolution.case_id, citations, resolution.linked_po_number
    ))
    return _result_from_resolution(
        "completed", input_type, input_value, resolution, parsed, findings, citations,
        line_links, tuple(calculation_notes),
    )


# Translate absent, uncertain, and conflicting source links into explicit review findings.
def _link_failure(
    resolution: InvoiceLinkResolution,
) -> tuple[Literal["invoice_link_unresolved"], str, str]:
    if resolution.link_status == "conflicting":
        return "invoice_link_unresolved", "PO_LINK_CONFLICT", "Printed, reviewed, and working-set PO references disagree."
    if resolution.link_status == "ambiguous":
        return "invoice_link_unresolved", "PO_LINK_AMBIGUOUS", "More than one PO candidate is present."
    if resolution.link_status == "unreviewed":
        return "invoice_link_unresolved", "PO_LINK_UNREVIEWED", "A working-set PO candidate has not been confirmed by a printed or reviewed link."
    if resolution.link_status == "record_missing":
        return "invoice_link_unresolved", "PO_NOT_FOUND", "The candidate PO number has no source PO record."
    return "invoice_link_unresolved", "PO_LINK_NOT_PROVIDED", "No printed or reviewed PO link is available."


# Propose only unique line links; require review whenever evidence is weaker than exact SKU/text.
def _propose_line_links(
    invoice: InvoiceCandidate,
    purchase_order: PurchaseOrderRecord,
    *,
    explicit_links: Mapping[int, int] | None,
    explicit_links_verified: bool,
) -> tuple[dict[int, int], tuple[LineLink, ...], list[Finding]]:
    if explicit_links is not None:
        links = dict(explicit_links)
        line_numbers = {line.line_no for line in purchase_order.lines}
        if any(index < 0 or index >= len(invoice.line_items) or line_no not in line_numbers for index, line_no in links.items()):
            raise ValueError("explicit line links must reference existing invoice indexes and PO line numbers")
        if len(set(links.values())) != len(links):
            raise ValueError("explicit line links cannot reuse one PO line")
        basis = "caller_verified" if explicit_links_verified else "caller_supplied_unverified"
        warnings = [] if explicit_links_verified else [Finding("LINE_LINK_REQUIRES_REVIEW", "Caller-supplied line links are not marked as owner-verified.")]
        po_by_line = {line.line_no: line for line in purchase_order.lines}
        link_records = tuple(
            _line_link(index, invoice.line_items[index], po_by_line[line_no], basis)
            for index, line_no in links.items()
        )
        return links, link_records, warnings

    links: dict[int, int] = {}
    link_records: list[LineLink] = []
    warnings: list[Finding] = []
    used_lines: set[int] = set()
    comparable_currency = bool(invoice.currency and invoice.currency.casefold() == purchase_order.currency.casefold())
    for index, invoice_line in enumerate(invoice.line_items):
        candidates = []
        basis = ""
        if invoice_line.sku:
            candidates = [line for line in purchase_order.lines if line.sku == invoice_line.sku]
            basis = "exact_sku"
        if not candidates and invoice_line.description:
            candidates = [
                line for line in purchase_order.lines
                if line.description and _normalize(line.description) == _normalize(invoice_line.description)
            ]
            basis = "exact_description"
        candidates = [line for line in candidates if line.line_no not in used_lines]
        if not candidates and comparable_currency and invoice_line.unit_price:
            invoice_price = invoice_line.decimal_value(invoice_line.unit_price)
            price_candidates = [
                line for line in purchase_order.lines
                if line.line_no not in used_lines
                and parse_decimal(line.unit_price, decimal_separator=".") == invoice_price
            ]
            if invoice_line.quantity:
                invoice_quantity = invoice_line.decimal_value(invoice_line.quantity)
                signature_candidates = [
                    line for line in price_candidates
                    if parse_decimal(line.quantity, decimal_separator=".") == invoice_quantity
                ]
            else:
                signature_candidates = []
            if len(signature_candidates) == 1:
                candidates, basis = signature_candidates, "unique_quantity_and_price"
            elif len(price_candidates) == 1:
                candidates, basis = price_candidates, "unique_unit_price"
        if not candidates and invoice_line.quantity:
            invoice_quantity = invoice_line.decimal_value(invoice_line.quantity)
            quantity_candidates = [
                line for line in purchase_order.lines
                if line.line_no not in used_lines
                and parse_decimal(line.quantity, decimal_separator=".") == invoice_quantity
            ]
            if len(quantity_candidates) == 1:
                candidates, basis = quantity_candidates, "unique_quantity"
        if len(candidates) != 1:
            warnings.append(Finding("LINE_LINK_UNRESOLVED", f"Invoice line {index + 1} has no unique PO line candidate."))
            continue
        matched = candidates[0]
        links[index] = matched.line_no
        used_lines.add(matched.line_no)
        link_records.append(_line_link(index, invoice_line, matched, basis))
    return links, tuple(link_records), warnings


# Retain the PO SKU and the evidence basis even when the invoice does not print a SKU.
def _line_link(
    index: int,
    invoice_line: InvoiceLineCandidate,
    po_line: PurchaseOrderLine,
    basis: str,
) -> LineLink:
    return LineLink(
        invoice_line_no=index + 1,
        invoice_description=invoice_line.description,
        invoice_sku=invoice_line.sku,
        po_line_no=po_line.line_no,
        po_description=po_line.description,
        po_sku=po_line.sku,
        basis=basis,
    )


# Convert source candidate strings to the mapping shape expected by deterministic reconciliation.
def _reconciliation_invoice(candidate: InvoiceCandidate) -> dict[str, object]:
    return {
        "po_number": candidate.po_number,
        "currency": candidate.currency,
        "line_items": [
            {"sku": line.sku, "description": line.description, "quantity": line.quantity,
             "unit_price": line.unit_price, "amount": line.amount}
            for line in candidate.line_items
        ],
        "subtotal": candidate.subtotal,
        "discount": candidate.discount if candidate.discount is not None else "0",
        "tax": candidate.tax,
        "total": candidate.total,
    }


# Flag another allow-listed invoice with the same exact printed invoice number.
def _duplicate_invoice_findings(
    loader: SourceRecordLoader,
    candidate: InvoiceCandidate,
    case_id: str,
    citations: list[str],
    current_po_number: str | None,
) -> list[Finding]:
    if not candidate.invoice_number:
        return []
    duplicates: list[str] = []
    for other_case, source in loader.working_invoice_paths:
        if other_case == case_id:
            continue
        other_path = loader.raw_root / source
        other = parse_invoice_pdf(str(other_path))
        if other.candidate.invoice_number == candidate.invoice_number:
            other_resolution = loader.resolve_invoice_path(source)
            if current_po_number and other_resolution.linked_po_number == current_po_number:
                duplicates.append(f"{other_case} (same PO {current_po_number})")
            else:
                duplicates.append(other_case)
            citations.append(_citation(_display_path(other_path), page_number=1))
    if duplicates:
        return [Finding(
            "DUPLICATE_INVOICE_NUMBER",
            f"Invoice number {candidate.invoice_number} also appears in: {', '.join(duplicates)}.",
        )]
    return []


# Keep invoice, PO, and receipt citations traceable to their source pages or record IDs.
def _candidate_citations(
    candidate: InvoiceCandidate,
    resolution: InvoiceLinkResolution,
) -> list[str]:
    cites = [_citation(candidate.source.source_path, page_number=candidate.source.page_number)]
    if resolution.purchase_order:
        cites.append(_locator_citation(resolution.purchase_order.source))
    cites.extend(_locator_citation(record.source) for record in resolution.receipt_records)
    return list(dict.fromkeys(cites))


# Format record provenance in the same page-or-record notation used by retrieval citations.
def _record_citations(
    purchase_order: PurchaseOrderRecord | None,
    receipts: tuple[GoodsReceiptRecord, ...],
) -> tuple[str, ...]:
    cites = ([_locator_citation(purchase_order.source)] if purchase_order else [])
    cites.extend(_locator_citation(receipt.source) for receipt in receipts)
    return tuple(dict.fromkeys(cites))


# Format a source path together with its one-based PDF page or stable JSON record ID.
def _locator_citation(locator) -> str:
    if locator.page_number is not None:
        return _citation(locator.source_path, page_number=locator.page_number)
    return f"{locator.source_path}, record {locator.record_id}"


# Keep one citation representation for page evidence in reports and terminal output.
def _citation(source_path: str, *, page_number: int) -> str:
    return f"{source_path}, page {page_number}"


# Normalize descriptions only for conservative exact text comparison.
def _normalize(value: str) -> str:
    return re.sub(r"\W+", " ", value.casefold()).strip()


# Expand common legal suffix abbreviations before comparing vendor names.
def _normalize_vendor(value: str) -> str:
    normalized = _normalize(value)
    normalized = re.sub(r"\bco$", "company", normalized)
    normalized = re.sub(r"\bcorp$", "corporation", normalized)
    normalized = re.sub(r"\binc$", "incorporated", normalized)
    normalized = re.sub(r"\bltd$", "limited", normalized)
    return normalized


# Return a path relative to the current project when the source file is inside it.
def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


# Build one immutable output object so unresolved and completed runs share a stable shape.
def _result_from_resolution(
    status: Literal["completed", "invoice_link_unresolved", "invoice_extraction_unsupported"],
    input_type: Literal["invoice_path", "po_number"],
    input_value: str,
    resolution: InvoiceLinkResolution,
    parsed: InvoiceParseResult,
    findings: list[Finding],
    citations: list[str],
    line_links: tuple[LineLink, ...],
    calculation_notes: tuple[str, ...] = (),
) -> ThreeWayResult:
    return ThreeWayResult(
        status=status,
        input_type=input_type,
        input_value=input_value,
        invoice_case_id=resolution.case_id,
        invoice_candidates=(resolution.case_id,),
        candidate=parsed.candidate,
        purchase_order=resolution.purchase_order,
        receipt_records=resolution.receipt_records,
        findings=tuple(findings),
        citations=tuple(dict.fromkeys(citations)),
        extraction_warnings=parsed.warnings,
        calculation_notes=calculation_notes,
        line_links=line_links,
        first_pass_review=resolution.first_pass_review,
        human_review_reasons=_human_review_reasons(findings, parsed),
        requires_human_review=bool(findings) or parsed.status != "complete",
    )


# Construct an output for PO-level failures without inventing invoice or field values.
def _empty_result(
    status: Literal["po_not_found", "invoice_not_found"],
    input_type: Literal["po_number"],
    input_value: str,
    findings: tuple[Finding, ...],
    citations: tuple[str, ...],
    *,
    purchase_order: PurchaseOrderRecord | None = None,
    receipt_records: tuple[GoodsReceiptRecord, ...] = (),
) -> ThreeWayResult:
    return ThreeWayResult(
        status=status,
        input_type=input_type,
        input_value=input_value,
        invoice_case_id=None,
        invoice_candidates=(),
        candidate=None,
        purchase_order=purchase_order,
        receipt_records=receipt_records,
        findings=findings,
        citations=citations,
        extraction_warnings=(),
        calculation_notes=(),
        line_links=(),
        first_pass_review="",
        human_review_reasons=tuple(item.message for item in findings),
        requires_human_review=True,
    )


# Explain every review flag in plain language, including incomplete extraction states.
def _human_review_reasons(findings: list[Finding], parsed: InvoiceParseResult) -> tuple[str, ...]:
    reasons = [item.message for item in findings]
    if parsed.status == "partial":
        reasons.append("Invoice parsing was partial; compare candidate fields with the source PDF.")
    elif parsed.status == "unsupported" and not reasons:
        reasons.append("Invoice text is unavailable; OCR or manual transcription is required.")
    return tuple(dict.fromkeys(reasons))


# Summarize invoice fields without embedding full PDF text in a run log.
def _invoice_summary(candidate: InvoiceCandidate) -> dict[str, object]:
    return {
        "invoice_number": candidate.invoice_number,
        "po_number_printed": candidate.po_number,
        "vendor": candidate.vendor,
        "currency": candidate.currency,
        "line_count": len(candidate.line_items),
        "subtotal": candidate.subtotal,
        "discount": candidate.discount,
        "tax": candidate.tax,
        "total": candidate.total,
        "source": _locator_citation(candidate.source),
    }


# Summarize the PO identity and source without copying all structured line text.
def _po_summary(record: PurchaseOrderRecord) -> dict[str, object]:
    return {"po_number": record.po_number, "vendor": record.vendor, "currency": record.currency,
            "line_count": len(record.lines), "source": _locator_citation(record.source)}


# Summarize each receipt by ID and PO link for the human reviewer.
def _receipt_summary(record: GoodsReceiptRecord) -> dict[str, object]:
    return {"receipt_id": record.receipt_id, "po_number": record.po_number,
            "line_count": len(record.lines), "source": _locator_citation(record.source)}
