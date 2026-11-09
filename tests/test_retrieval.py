import pytest

from src.chunking import TextChunk
from src.retrieval import retrieve_evidence
from src.vector_store import rebuild_collection


class FakeEmbedder:
    def embed(self, texts):
        assert len(texts) == 1
        return [[1.0, 0.0, 0.0]]


def make_collection(tmp_path):
    chunks = [
        TextChunk("invoice-1:p2:c0", "invoice-1", "invoices/one.pdf", 2, 0, "Invoice total 12.50 USD"),
        TextChunk("po-1:record", "PO-1", "purchase_orders.json", 0, 0, '{"po_number":"PO-1"}', "purchase_order", "PO-1"),
    ]
    return rebuild_collection(
        tmp_path / "chroma",
        "evidence",
        chunks,
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        embedding_model="test-embedder",
        dimensions=3,
    )


def test_retrieval_returns_source_page_citation_and_metadata_filter(tmp_path):
    collection = make_collection(tmp_path)

    results = retrieve_evidence("What is the invoice total?", FakeEmbedder(), collection, where={"source_id": "invoice-1"})

    assert len(results) == 1
    assert results[0].text == "Invoice total 12.50 USD"
    assert results[0].citation.format() == "invoices/one.pdf, page 2"
    assert results[0].document_type == "invoice_pdf"


def test_structured_record_citation_uses_record_id(tmp_path):
    collection = make_collection(tmp_path)

    results = retrieve_evidence("Find PO", FakeEmbedder(), collection, where={"document_type": "purchase_order"})

    assert len(results) == 1
    assert results[0].citation.format() == "purchase_orders.json, record PO-1"


def test_empty_question_and_no_match_are_handled(tmp_path):
    collection = make_collection(tmp_path)
    with pytest.raises(ValueError, match="question must not be empty"):
        retrieve_evidence("  ", FakeEmbedder(), collection)

    results = retrieve_evidence("no matching source", FakeEmbedder(), collection, where={"source_id": "missing"})
    assert results == []
