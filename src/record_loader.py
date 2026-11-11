"""Load allow-listed source records and resolve invoice, PO, and GR links exactly."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from src.extraction import extract_pdf
from src.schemas import GoodsReceiptRecord, PurchaseOrderRecord


PO_PATTERN = re.compile(r"(?<![A-Z0-9])PO-\d{4}-\d{4}(?![A-Z0-9])")


@dataclass(frozen=True)
class InvoiceLinkResolution:
    """Describe an allow-listed invoice and its source-linked records."""

    case_id: str
    invoice_source: str
    extraction_status: str
    printed_po_numbers: tuple[str, ...]
    owner_review_po_candidates: tuple[str, ...]
    working_set_po_candidates: tuple[str, ...]
    linked_po_number: str | None
    link_status: Literal["linked", "missing", "unreviewed", "ambiguous", "conflicting", "record_missing"]
    review_status: str
    first_pass_review: str
    purchase_order: PurchaseOrderRecord | None
    receipt_records: tuple[GoodsReceiptRecord, ...]
    receipt_status: Literal["available", "missing", "not_required", "unknown"]


@dataclass(frozen=True)
class PurchaseOrderResolution:
    """Return one exact PO, every receipt for it, and possible invoice cases."""

    po_number: str
    status: Literal["found", "not_found"]
    purchase_order: PurchaseOrderRecord | None
    receipt_records: tuple[GoodsReceiptRecord, ...]
    receipt_status: Literal["available", "missing", "not_required", "unknown"]
    invoice_candidates: tuple[InvoiceLinkResolution, ...]


class SourceRecordLoader:
    """Resolve only working-set invoice files and exact PO/receipt identifiers."""

    def __init__(
        self,
        raw_data_dir: str | Path = "data/raw/invoice-agent",
        working_set_csv: str | Path = "eval/working_set.csv",
        review_queue_csv: str | Path = "eval/review_queue.csv",
    ) -> None:
        self.raw_root = Path(raw_data_dir).resolve()
        self._working_rows = self._load_unique_csv_rows(working_set_csv, "case_id")
        self._review_rows = self._load_unique_csv_rows(review_queue_csv, "case_id")
        self._review_by_case = {row["case_id"]: row for row in self._review_rows}
        self._allowed_paths = self._build_invoice_allowlist()
        self._purchase_orders = self._load_purchase_orders()
        self._receipts = self._load_receipts()
        self._invoice_cache: dict[str, InvoiceLinkResolution] = {}

    # Resolve one supplied invoice path only when it maps to an allow-listed row.
    def resolve_invoice_path(self, invoice_path: str | Path) -> InvoiceLinkResolution:
        absolute_path = self._find_allowlisted_path(invoice_path)
        row = self._allowed_paths[absolute_path]
        case_id = row["case_id"]
        if case_id not in self._invoice_cache:
            self._invoice_cache[case_id] = self._resolve_invoice_row(row)
        return self._invoice_cache[case_id]

    # Expose only allow-listed invoice identifiers and paths for duplicate detection.
    @property
    def working_invoice_paths(self) -> tuple[tuple[str, str], ...]:
        return tuple((row["case_id"], row["invoice_source"]) for row in self._working_rows)

    # Find a PO exactly, then attach all GRs sharing its po_number and matching invoices.
    def resolve_po_number(self, po_number: str) -> PurchaseOrderResolution:
        if not isinstance(po_number, str) or not re.fullmatch(r"PO-\d{4}-\d{4}", po_number):
            raise ValueError("po_number must exactly match PO-YYYY-NNNN")
        purchase_order = self._purchase_orders.get(po_number)
        if purchase_order is None:
            return PurchaseOrderResolution(po_number, "not_found", None, (), "unknown", ())

        receipts = tuple(record for record in self._receipts.values() if record.po_number == po_number)
        receipt_status = self._receipt_status(purchase_order, receipts)
        invoices = tuple(
            self.resolve_invoice_path(row["invoice_source"])
            for row in self._working_rows
            if self._invoice_matches_po(row, po_number)
        )
        return PurchaseOrderResolution(po_number, "found", purchase_order, receipts, receipt_status, invoices)

    # Read CSV rows by a stable key and reject duplicate IDs before building indexes.
    @staticmethod
    def _load_unique_csv_rows(path: str | Path, key: str) -> list[dict[str, str]]:
        with Path(path).open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        seen: set[str] = set()
        for row in rows:
            value = row.get(key, "")
            if not value or value in seen:
                raise ValueError(f"CSV {path} contains a missing or duplicate {key}")
            seen.add(value)
        return rows

    # Canonicalize manifest paths and ensure every allowed invoice remains below the raw root.
    def _build_invoice_allowlist(self) -> dict[Path, dict[str, str]]:
        allowed: dict[Path, dict[str, str]] = {}
        for row in self._working_rows:
            source = row.get("invoice_source", "")
            if not source:
                raise ValueError(f"Working-set case {row['case_id']} has no invoice_source")
            path = (self.raw_root / source).resolve()
            if not path.is_relative_to(self.raw_root) or path.suffix.casefold() != ".pdf":
                raise ValueError(f"Working-set invoice path is outside the PDF allowlist: {source}")
            if path in allowed:
                raise ValueError(f"Working set maps multiple cases to the same invoice path: {source}")
            allowed[path] = row
        return allowed

    # Locate a caller path through canonical equality with the working-set allowlist.
    def _find_allowlisted_path(self, invoice_path: str | Path) -> Path:
        supplied = Path(invoice_path).expanduser()
        candidates = [supplied.resolve()] if supplied.is_absolute() else [
            (self.raw_root / supplied).resolve(),
            (Path.cwd() / supplied).resolve(),
        ]
        matches = [candidate for candidate in candidates if candidate in self._allowed_paths]
        if not matches:
            raise ValueError("invoice_path is not present in eval/working_set.csv")
        return matches[0]

    # Parse JSON records into strict models and reject duplicate PO identifiers.
    def _load_purchase_orders(self) -> dict[str, PurchaseOrderRecord]:
        path = self.raw_root / "purchase_orders.json"
        raw_records = self._read_json_list(path)
        records: dict[str, PurchaseOrderRecord] = {}
        for raw in raw_records:
            po_number = raw.get("po_number") if isinstance(raw, dict) else None
            if not isinstance(po_number, str) or po_number in records:
                raise ValueError("purchase_orders.json contains a missing or duplicate po_number")
            source = {"source_path": self._display_path(path), "record_id": po_number}
            records[po_number] = PurchaseOrderRecord.model_validate({**raw, "source": source})
        return records

    # Parse receipt JSON into strict models and reject duplicate receipt identifiers.
    def _load_receipts(self) -> dict[str, GoodsReceiptRecord]:
        path = self.raw_root / "receipts.json"
        raw_records = self._read_json_list(path)
        records: dict[str, GoodsReceiptRecord] = {}
        for raw in raw_records:
            receipt_id = raw.get("receipt_id") if isinstance(raw, dict) else None
            if not isinstance(receipt_id, str) or receipt_id in records:
                raise ValueError("receipts.json contains a missing or duplicate receipt_id")
            source = {"source_path": self._display_path(path), "record_id": receipt_id}
            records[receipt_id] = GoodsReceiptRecord.model_validate({**raw, "source": source})
        return records

    # Require a JSON list of object records without exposing document contents in errors.
    @staticmethod
    def _read_json_list(path: Path) -> list[dict[str, object]]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not load source record file: {path.name}") from exc
        if not isinstance(data, list) or any(not isinstance(record, dict) for record in data):
            raise ValueError(f"Source record file must contain a JSON list of objects: {path.name}")
        return data

    # Resolve printed and explicitly reviewed PO IDs without treating unreviewed pointers as links.
    def _resolve_invoice_row(self, row: dict[str, str]) -> InvoiceLinkResolution:
        path = self._path_for_row(row)
        extraction = extract_pdf(path, source_id=row["case_id"])
        text = "\n".join(page.text for page in extraction.pages)
        printed_ids = tuple(sorted(set(PO_PATTERN.findall(text))))
        review = self._review_by_case.get(row["case_id"], {})
        review_status = review.get("review_status", "not_reviewed")
        owner_text = review.get("owner_verified_po_gr_links", "")
        reviewed_ids = tuple(sorted(set(PO_PATTERN.findall(owner_text)))) if review_status == "reviewed" else ()
        working_ids = tuple(sorted(set(PO_PATTERN.findall(row.get("po_record_reference", "")))))
        eligible = set(printed_ids) | set(reviewed_ids)
        conflict = len(printed_ids) > 1 or len(reviewed_ids) > 1 or len(eligible) > 1
        if working_ids and eligible and set(working_ids) != eligible:
            conflict = True

        linked_id = next(iter(eligible)) if len(eligible) == 1 and not conflict else None
        if conflict:
            link_status = "conflicting"
        elif linked_id is not None and linked_id not in self._purchase_orders:
            link_status = "record_missing"
        elif linked_id is not None:
            link_status = "linked"
        elif working_ids:
            link_status = "unreviewed"
        else:
            link_status = "missing"

        purchase_order = self._purchase_orders.get(linked_id) if link_status == "linked" else None
        receipts = tuple(
            record for record in self._receipts.values()
            if purchase_order is not None and record.po_number == purchase_order.po_number
        )
        receipt_status = self._receipt_status(purchase_order, receipts)
        return InvoiceLinkResolution(
            case_id=row["case_id"],
            invoice_source=row["invoice_source"],
            extraction_status=extraction.status,
            printed_po_numbers=printed_ids,
            owner_review_po_candidates=reviewed_ids,
            working_set_po_candidates=working_ids,
            linked_po_number=linked_id,
            link_status=link_status,
            review_status=review_status,
            first_pass_review=review.get("owner_verified_expected_findings", ""),
            purchase_order=purchase_order,
            receipt_records=receipts,
            receipt_status=receipt_status,
        )

    # Search indexed working-set invoices by exact printed or reviewed PO number.
    def _invoice_matches_po(self, row: dict[str, str], po_number: str) -> bool:
        path = self._path_for_row(row)
        extraction = extract_pdf(path, source_id=row["case_id"])
        printed_ids = set(PO_PATTERN.findall("\n".join(page.text for page in extraction.pages)))
        review = self._review_by_case.get(row["case_id"], {})
        reviewed_ids = set()
        if review.get("review_status") == "reviewed":
            reviewed_ids = set(PO_PATTERN.findall(review.get("owner_verified_po_gr_links", "")))
        return po_number in printed_ids or po_number in reviewed_ids

    # Join the raw-data root and an allow-listed relative invoice path.
    def _path_for_row(self, row: dict[str, str]) -> Path:
        path = (self.raw_root / row["invoice_source"]).resolve()
        if path not in self._allowed_paths:
            raise ValueError("Working-set invoice path is not in the validated allowlist")
        if not path.is_file():
            raise FileNotFoundError(f"Allow-listed invoice file is missing: {row['invoice_source']}")
        return path

    # Return a repository-relative locator when possible, otherwise preserve the absolute source path.
    @staticmethod
    def _display_path(path: Path) -> str:
        resolved = path.resolve()
        try:
            return resolved.relative_to(Path.cwd().resolve()).as_posix()
        except ValueError:
            return resolved.as_posix()

    # Distinguish available receipts from required-but-missing and not-required receipts.
    @staticmethod
    def _receipt_status(
        purchase_order: PurchaseOrderRecord | None,
        receipts: tuple[GoodsReceiptRecord, ...],
    ) -> Literal["available", "missing", "not_required", "unknown"]:
        if purchase_order is None:
            return "unknown"
        if receipts:
            return "available"
        return "missing" if purchase_order.receipt_required else "not_required"
