import json
from io import BytesIO
from unittest.mock import patch

import pytest

from src.generation import ABSTENTION, answer_with_evidence
from src.retrieval import Citation, RetrievedEvidence


def response(text):
    return BytesIO(json.dumps({"message": {"content": text}}).encode("utf-8"))


def evidence():
    return [
        RetrievedEvidence(
            "invoice:p1:c0",
            "invoice-1",
            "invoice_pdf",
            "Invoice total is USD 25.00.",
            Citation("invoices/one.pdf", page_number=1),
            0.1,
        )
    ]


def test_prompt_cites_retrieved_evidence_and_uses_requested_context():
    with patch("src.generation.urlopen", return_value=response("The total is USD 25.00 [E1].")) as mocked:
        answer = answer_with_evidence("What is the total?", evidence(), model="phi4-mini:latest", num_ctx=4096)

    request = mocked.call_args.args[0]
    payload = json.loads(request.data)
    assert payload["model"] == "phi4-mini:latest"
    assert payload["options"]["num_ctx"] == 4096
    assert "Invoice total is USD 25.00." in payload["messages"][1]["content"]
    assert "[E1] invoices/one.pdf, page 1" in payload["messages"][1]["content"]
    assert answer.text == "The total is USD 25.00 [E1]."
    assert answer.citations[0].format() == "invoices/one.pdf, page 1"
    assert answer.abstained is False


def test_no_evidence_abstains_without_calling_ollama():
    with patch("src.generation.urlopen") as mocked:
        answer = answer_with_evidence("What is the total?", [], model="phi4-mini:latest")

    mocked.assert_not_called()
    assert answer.text == ABSTENTION
    assert answer.abstained is True


@pytest.mark.parametrize("model_text", ["The total is USD 25.00.", "The total is USD 25.00 [E2]."])
def test_uncited_or_unknown_citation_abstains(model_text):
    with patch("src.generation.urlopen", return_value=response(model_text)):
        answer = answer_with_evidence("What is the total?", evidence(), model="phi4-mini:latest")

    assert answer.text == ABSTENTION
    assert answer.citations == ()
    assert answer.abstained is True


def test_rejects_non_local_generation_endpoint():
    with pytest.raises(ValueError, match="local Ollama"):
        answer_with_evidence("Question?", evidence(), model="model", base_url="https://example.com")
