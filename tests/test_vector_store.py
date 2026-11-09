import pytest

from src.chunking import TextChunk
from src.vector_store import query_by_embedding, rebuild_collection


def chunks():
    return [
        TextChunk("invoice-a:p1:c0", "invoice-a", "invoices/a.pdf", 1, 0, "Invoice total 25.00 USD"),
        TextChunk("po-a:p2:c0", "po-a", "records/po-a.json", 2, 0, "PO line price 25.00 USD"),
    ]


def test_stores_explicit_vectors_and_queries_with_source_page_metadata(tmp_path):
    collection = rebuild_collection(
        tmp_path / "chroma",
        "evidence",
        chunks(),
        [[1.0, 0.0, 0.0], [0.9, 0.1, 0.0]],
        embedding_model="test-embedder",
        dimensions=3,
    )

    assert collection.count() == 2
    query = query_by_embedding(collection, [1.0, 0.0, 0.0], n_results=1, where={"source_id": "invoice-a"})
    assert query["ids"] == [["invoice-a:p1:c0"]]
    assert query["metadatas"][0][0]["source_path"] == "invoices/a.pdf"
    assert query["metadatas"][0][0]["page_number"] == 1
    assert query["documents"][0][0] == "Invoice total 25.00 USD"
    assert collection.metadata["embedding_model"] == "test-embedder"
    assert collection.metadata["embedding_dimensions"] == 3
    assert collection._embedding_function is None


def test_rebuild_removes_stale_records_and_preserves_current_records(tmp_path):
    path = tmp_path / "chroma"
    first = rebuild_collection(path, "evidence", chunks(), [[1, 0], [0, 1]], embedding_model="m", dimensions=2)
    assert first.count() == 2

    second = rebuild_collection(path, "evidence", chunks()[:1], [[1, 0]], embedding_model="m", dimensions=2)

    assert second.count() == 1
    assert second.get()["ids"] == ["invoice-a:p1:c0"]


def test_invalid_rebuild_input_does_not_delete_existing_collection(tmp_path):
    path = tmp_path / "chroma"
    good = rebuild_collection(path, "evidence", chunks()[:1], [[1, 0]], embedding_model="m", dimensions=2)

    with pytest.raises(ValueError, match="dimension"):
        rebuild_collection(path, "evidence", chunks()[:1], [[1, 0, 0]], embedding_model="m", dimensions=2)

    assert good.count() == 1


def test_rejects_duplicate_ids_non_finite_vectors_and_bad_query_dimensions(tmp_path):
    duplicate = [chunks()[0], chunks()[0]]
    with pytest.raises(ValueError, match="unique"):
        rebuild_collection(tmp_path / "bad", "evidence", duplicate, [[1, 0], [0, 1]], embedding_model="m", dimensions=2)

    collection = rebuild_collection(tmp_path / "chroma", "evidence", chunks()[:1], [[1, 0]], embedding_model="m", dimensions=2)
    with pytest.raises(ValueError, match="non-finite"):
        rebuild_collection(tmp_path / "other", "evidence", chunks()[:1], [[float("nan"), 0]], embedding_model="m", dimensions=2)
    with pytest.raises(ValueError, match="dimension"):
        query_by_embedding(collection, [1.0], n_results=1)
