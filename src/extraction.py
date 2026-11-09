"""Selectable-text PDF extraction with source and page provenance.

Scanned PDFs are reported as unsupported; this module deliberately performs no OCR.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass(frozen=True)
class PageText:
    source_id: str
    source_path: str
    page_number: int  # One-based, for citations.
    text: str


@dataclass(frozen=True)
class ExtractionResult:
    source_id: str
    source_path: str
    status: str  # selectable_text, no_text_layer, or empty_pdf
    pages: tuple[PageText, ...]


# Keep each page tied to its source so later retrieval can cite the exact location.
def extract_pdf(path: str | Path, *, source_id: str | None = None) -> ExtractionResult:
    """Extract text page by page, preserving a stable source ID and relative path."""
    pdf_path = Path(path)
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {pdf_path.name}")

    stable_id = source_id or pdf_path.stem
    display_path = pdf_path.as_posix()
    try:
        with pymupdf.open(pdf_path) as document:
            pages = tuple(
                PageText(
                    source_id=stable_id,
                    source_path=display_path,
                    page_number=index + 1,
                    text=page.get_text("text").strip(),
                )
                for index, page in enumerate(document)
            )
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise ValueError(f"Could not read PDF {pdf_path}: {exc}") from exc

    if not pages:
        status = "empty_pdf"
    elif not any(page.text for page in pages):
        status = "no_text_layer"
    else:
        status = "selectable_text"
    return ExtractionResult(stable_id, display_path, status, pages)
