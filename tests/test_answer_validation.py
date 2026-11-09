from src.answer_validation import validate_numeric_claims
from src.generation import GroundedAnswer
from src.retrieval import Citation, RetrievedEvidence


def evidence(text, *, source_id="invoice-1"):
    citation = Citation("invoices/one.pdf", page_number=1)
    return RetrievedEvidence("invoice:p1:c0", source_id, "invoice_pdf", text, citation, 0.1)


def test_validates_comma_decimal_answer_against_dot_decimal_source():
    source = evidence("Unit price is EUR 12.50.")
    answer = GroundedAnswer("The unit price is EUR 12,5 [E1].", (source.citation,), False)

    result = validate_numeric_claims(answer, [source])

    assert result.supported is True
    assert result.checked_values == ("12,5",)
    assert result.unsupported_values == ()


def test_flags_wrong_numeric_value_in_cited_evidence():
    source = evidence("Invoice amount is 40.35 USD.")
    answer = GroundedAnswer("The amount is 403.50 USD [E1].", (source.citation,), False)

    result = validate_numeric_claims(answer, [source])

    assert result.supported is False
    assert "403.50" in result.unsupported_values


def test_uses_only_the_sources_cited_by_the_answer():
    first = evidence("Invoice total is 40.35 USD.")
    second = RetrievedEvidence("po:record", "PO-1", "purchase_order", "Amount 403.50 USD", Citation("po.json", record_id="PO-1"), 0.2)
    answer = GroundedAnswer("The amount is 403.50 USD [E1].", (first.citation,), False)

    result = validate_numeric_claims(answer, [first, second])

    assert result.supported is False
    assert result.unsupported_values == ("403.50",)


def test_marks_ambiguous_single_separator_thousands_value_for_review():
    source = evidence("Balance 1.234.")
    answer = GroundedAnswer("The balance is 1,234 [E1].", (source.citation,), False)

    result = validate_numeric_claims(answer, [source])

    assert result.supported is False
    assert result.ambiguous_values == ("1,234",)


def test_abstentions_and_answers_without_numbers_pass_without_numeric_claims():
    source = evidence("The invoice is marked paid.")
    abstention = GroundedAnswer("I can't answer from the available documents.", (), True)
    text_answer = GroundedAnswer("The invoice is marked paid [E1].", (source.citation,), False)

    assert validate_numeric_claims(abstention, []).supported is True
    result = validate_numeric_claims(text_answer, [source])
    assert result.supported is True
    assert result.checked_values == ()
