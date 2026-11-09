from decimal import Decimal

from src.reconciliation import (
    check_invoice_totals,
    compare_currency,
    compare_invoice_line,
    parse_decimal,
)


def test_decimal_parser_preserves_precision_and_equivalent_spellings():
    assert parse_decimal("12.10") == parse_decimal("12.1") == Decimal("12.1")
    assert parse_decimal("403.50") != parse_decimal("40.35")
    assert parse_decimal("-12.10") == Decimal("-12.10")


def test_decimal_parser_requires_explicit_locale_and_supports_grouping():
    assert parse_decimal("1.234,50", decimal_separator=",", grouping_separator=".") == Decimal("1234.50")
    assert parse_decimal("23,40", decimal_separator=",") == Decimal("23.40")


def test_decimal_parser_rejects_float_and_malformed_values():
    try:
        parse_decimal(0.1)  # type: ignore[arg-type]
    except TypeError:
        pass
    else:
        raise AssertionError("float input should be rejected")
    for value in ("", "1,2.3", "1.2.3", "1,23,4"):
        try:
            parse_decimal(value, decimal_separator=".", grouping_separator=",")
        except ValueError:
            continue
        raise AssertionError(f"malformed input should be rejected: {value!r}")


def test_line_comparison_flags_price_quantity_receipt_and_money_mismatch():
    findings = compare_invoice_line(
        {"quantity": "4", "unit_price": "61.56"},
        {"quantity": "3", "unit_price": "57.00"},
        receipt_lines=[{"quantity": "2"}],
    )
    assert {finding.code for finding in findings} == {
        "PRICE_VARIANCE",
        "QTY_EXCEEDS_ORDERED",
        "PO_GR_QTY_MISMATCH",
        "QTY_EXCEEDS_RECEIVED",
    }


def test_any_exact_price_difference_is_flagged_without_one_percent_tolerance():
    findings = compare_invoice_line(
        {"quantity": "1", "unit_price": "101.00"},
        {"quantity": "1", "unit_price": "100.00"},
    )
    assert [finding.code for finding in findings] == ["PRICE_VARIANCE"]


def test_unreviewed_and_missing_receipts_are_distinct():
    invoice_line = {"quantity": "1", "unit_price": "2.00"}
    po_line = {"quantity": "1", "unit_price": "2.00"}
    assert compare_invoice_line(invoice_line, po_line, receipt_lines=None) == []
    assert [f.code for f in compare_invoice_line(invoice_line, po_line, receipt_lines=[])] == ["RECEIPT_MISSING"]


def test_invoice_line_extension_and_totals_use_exact_decimal_arithmetic():
    invoice = {
        "line_items": [{"quantity": "6", "unit_price": "12.25", "amount": "73.50"}],
        "subtotal": "73.50",
        "discount": "0.00",
        "tax": "14.70",
        "total": "88.20",
    }
    assert check_invoice_totals(invoice) == []

    invoice["total"] = "98.20"
    assert [f.code for f in check_invoice_totals(invoice)] == ["TOTAL_MISMATCH"]


def test_invoice_total_difference_is_not_silently_rounded():
    invoice = {
        "line_items": [{"quantity": "1", "unit_price": "0.005", "amount": "0.005"}],
        "subtotal": "0.005",
        "discount": "0",
        "tax": "0",
        "total": "0.01",
    }
    assert "TOTAL_MISMATCH" in {f.code for f in check_invoice_totals(invoice)}


def test_line_extension_and_missing_money_field_are_reported():
    bad_extension = {
        "line_items": [{"quantity": "2", "unit_price": "5.00", "amount": "9.99"}],
        "subtotal": "9.99",
        "discount": "0.00",
        "tax": "0.00",
        "total": "9.99",
    }
    assert [f.code for f in check_invoice_totals(bad_extension)] == ["LINE_AMOUNT_MISMATCH"]

    del bad_extension["line_items"][0]["amount"]
    assert check_invoice_totals(bad_extension)[0].code == "INVALID_OR_MISSING_AMOUNT"


def test_currency_mismatch_is_flagged_without_conversion():
    assert [f.code for f in compare_currency("USD", "EUR")] == ["CURRENCY_MISMATCH"]
    assert compare_currency("GBP", "gbp") == []


def test_malformed_amount_is_returned_as_review_finding():
    invoice = {
        "line_items": [{"quantity": "2", "unit_price": "bad", "amount": "10.00"}],
        "subtotal": "10.00",
        "discount": "0.00",
        "tax": "0.00",
        "total": "10.00",
    }
    assert check_invoice_totals(invoice)[0].code == "INVALID_OR_MISSING_AMOUNT"
