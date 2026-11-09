"""Simple paragraph-aware chunks that retain source and page identity."""

from __future__ import annotations

from dataclasses import dataclass

from src.extraction import PageText


@dataclass(frozen=True)
class TextChunk:
    chunk_id: str
    source_id: str
    source_path: str
    page_number: int
    chunk_index: int
    text: str
    document_type: str = "invoice_pdf"
    record_id: str | None = None


# Bound chunk size while keeping source and page metadata for citations.
def chunk_pages(pages: tuple[PageText, ...] | list[PageText], *, max_chars: int = 1000) -> list[TextChunk]:
    """Pack paragraphs into bounded chunks; split oversized paragraphs safely.

    Empty pages produce no chunk. Page numbers remain one-based and chunk indexes
    restart on each page so every result has a direct citation location.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1")

    chunks: list[TextChunk] = []
    for page in pages:
        paragraphs = [part.strip() for part in page.text.split("\n\n") if part.strip()]
        pieces: list[str] = []
        for paragraph in paragraphs:
            if len(paragraph) <= max_chars:
                pieces.append(paragraph)
            else:
                pieces.extend(paragraph[start : start + max_chars] for start in range(0, len(paragraph), max_chars))

        page_chunks: list[str] = []
        current = ""
        for piece in pieces:
            candidate = f"{current}\n\n{piece}" if current else piece
            if current and len(candidate) > max_chars:
                page_chunks.append(current)
                current = piece
            else:
                current = candidate
        if current:
            page_chunks.append(current)

        for index, text in enumerate(page_chunks):
            chunks.append(
                TextChunk(
                    chunk_id=f"{page.source_id}:p{page.page_number}:c{index}",
                    source_id=page.source_id,
                    source_path=page.source_path,
                    page_number=page.page_number,
                    chunk_index=index,
                    text=text,
                )
            )
    return chunks
