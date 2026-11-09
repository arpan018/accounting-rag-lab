import pymupdf
import pytest

from src.chunking import chunk_pages
from src.extraction import PageText, extract_pdf


def make_pdf(path, *, text=None, pages=1):
    document = pymupdf.open()
    for index in range(pages):
        page = document.new_page()
        if text is not None and index == 0:
            page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def test_extracts_selectable_text_with_one_based_page_provenance(tmp_path):
    pdf = tmp_path / "invoice.pdf"
    make_pdf(pdf, text="Invoice total 12.34")

    result = extract_pdf(pdf, source_id="inv-1")

    assert result.status == "selectable_text"
    assert result.pages[0].source_id == "inv-1"
    assert result.pages[0].page_number == 1
    assert "12.34" in result.pages[0].text


def test_reports_empty_page_and_keeps_page_number(tmp_path):
    pdf = tmp_path / "two-pages.pdf"
    make_pdf(pdf, text="First page", pages=2)

    result = extract_pdf(pdf)

    assert result.status == "selectable_text"
    assert [page.page_number for page in result.pages] == [1, 2]
    assert result.pages[1].text == ""


def test_reports_scanned_or_image_only_pdf_without_ocr(tmp_path):
    pdf = tmp_path / "scan.pdf"
    make_pdf(pdf)

    result = extract_pdf(pdf)

    assert result.status == "no_text_layer"
    assert result.pages[0].text == ""
    assert chunk_pages(result.pages) == []


def test_rejects_non_pdf_input(tmp_path):
    source = tmp_path / "invoice.txt"
    source.write_text("not a pdf")

    with pytest.raises(ValueError, match="Expected a PDF"):
        extract_pdf(source)


def test_chunking_keeps_page_citation_and_respects_size():
    pages = [PageText("doc", "invoices/a.pdf", 3, "one\ntwo\n\nlonger paragraph")]

    chunks = chunk_pages(pages, max_chars=8)

    assert chunks
    assert all(chunk.page_number == 3 for chunk in chunks)
    assert all(chunk.source_path == "invoices/a.pdf" for chunk in chunks)
    assert all(len(chunk.text) <= 8 for chunk in chunks)
