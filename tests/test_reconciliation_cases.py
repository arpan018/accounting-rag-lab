"""T09 smoke cases transcribed from the owner-reviewed invoice, PO, and receipt sources."""

from src.reconciliation import reconcile_invoice


def test_case_015_flags_sub_one_percent_price_difference():
    invoice = {
        "po_number": "PO-2026-0113",
        "currency": "EUR",
        "line_items": [
            {"sku": "BF-40660", "quantity": "20", "unit_price": "15,45", "amount": "309,00"},
            {"sku": "BF-40110", "quantity": "100", "unit_price": "4,85", "amount": "485,00"},
        ],
        "subtotal": "794,00",
        "discount": "0,00",
        "tax": "150,86",
        "total": "944,86",
    }
    po = {
        "po_number": "PO-2026-0113",
        "currency": "EUR",
        "lines": [
            {"line_no": 1, "sku": "BF-40660", "quantity": "20", "unit_price": "15.30"},
            {"line_no": 2, "sku": "BF-40110", "quantity": "100", "unit_price": "4.85"},
        ],
    }
    receipts = [{"po_number": "PO-2026-0113", "lines": [{"line_no": 1, "quantity": "20"}, {"line_no": 2, "quantity": "100"}]}]

    findings = reconcile_invoice(invoice, po, receipts, decimal_separator=",", po_decimal_separator=".")

    assert [finding.code for finding in findings] == ["PRICE_VARIANCE"]


def test_case_016_flags_unit_price_variance_with_different_source_separators():
    invoice = {
        "po_number": "PO-2026-0114",
        "currency": "EUR",
        "line_items": [
            {"sku": "BF-40440", "quantity": "4", "unit_price": "61,56", "amount": "246,24"},
            {"sku": "BF-40550", "quantity": "10", "unit_price": "9,75", "amount": "97,50"},
        ],
        "subtotal": "343,74",
        "discount": "0,00",
        "tax": "65,31",
        "total": "409,05",
    }
    po = {
        "po_number": "PO-2026-0114",
        "currency": "EUR",
        "lines": [
            {"line_no": 1, "sku": "BF-40440", "quantity": "4", "unit_price": "57.00"},
            {"line_no": 2, "sku": "BF-40550", "quantity": "10", "unit_price": "9.75"},
        ],
    }
    receipts = [{"po_number": "PO-2026-0114", "lines": [{"line_no": 1, "quantity": "4"}, {"line_no": 2, "quantity": "10"}]}]

    findings = reconcile_invoice(invoice, po, receipts, decimal_separator=",", po_decimal_separator=".")

    assert [finding.code for finding in findings] == ["PRICE_VARIANCE"]


def test_case_026_flags_invoice_total_difference_after_line_arithmetic():
    invoice = {
        "po_number": "PO-2026-0123",
        "currency": "GBP",
        "line_items": [
            {"sku": "KLC-2203", "quantity": "6", "unit_price": "12.25", "amount": "73.50"},
            {"sku": "KLC-2204", "quantity": "5", "unit_price": "6.80", "amount": "34.00"},
        ],
        "subtotal": "107.50",
        "discount": "0.00",
        "tax": "21.50",
        "total": "139.00",
    }
    po = {
        "po_number": "PO-2026-0123",
        "currency": "GBP",
        "lines": [
            {"line_no": 1, "sku": "KLC-2203", "quantity": "6", "unit_price": "12.25"},
            {"line_no": 2, "sku": "KLC-2204", "quantity": "5", "unit_price": "6.80"},
        ],
    }
    receipts = [{"po_number": "PO-2026-0123", "lines": [{"line_no": 1, "quantity": "6"}, {"line_no": 2, "quantity": "5"}]}]

    findings = reconcile_invoice(invoice, po, receipts)

    assert [finding.code for finding in findings] == ["TOTAL_MISMATCH"]


def test_case_019_currency_mismatch_is_flagged_without_cross_currency_price_comparison():
    invoice = {
        "po_number": "PO-2026-0116",
        "currency": "USD",
        "line_items": [{"sku": "BF-40220", "quantity": "4", "unit_price": "23,40", "amount": "93,60"}],
        "subtotal": "93,60",
        "discount": "0,00",
        "tax": "17,78",
        "total": "111,38",
    }
    po = {"po_number": "PO-2026-0116", "currency": "EUR", "lines": [{"line_no": 1, "sku": "BF-40220", "quantity": "4", "unit_price": "23.40"}]}
    receipts = [{"po_number": "PO-2026-0116", "lines": [{"line_no": 1, "quantity": "4"}]}]

    findings = reconcile_invoice(invoice, po, receipts, decimal_separator=",", po_decimal_separator=".")

    assert [finding.code for finding in findings] == ["CURRENCY_MISMATCH"]


def test_case_005_keeps_invoice_omission_separate_from_reviewed_po_link():
    invoice = {
        "po_number": None,
        "currency": "USD",
        "line_items": [
            {"description": "Ballpoint pens, blue, box of 50", "quantity": "6", "unit_price": "11.90", "amount": "71.40"},
            {"description": "Lever arch file, A4, black", "quantity": "40", "unit_price": "4.15", "amount": "166.00"},
        ],
        "subtotal": "237.40",
        "discount": "0.00",
        "tax": "19.59",
        "total": "256.99",
    }
    po = {
        "po_number": "PO-2026-0105",
        "currency": "USD",
        "lines": [
            {"line_no": 1, "sku": "QOS-1002", "quantity": "6", "unit_price": "11.90"},
            {"line_no": 2, "sku": "QOS-1005", "quantity": "40", "unit_price": "4.15"},
        ],
    }
    receipts = [{"po_number": "PO-2026-0105", "lines": [{"line_no": 1, "quantity": "6"}, {"line_no": 2, "quantity": "40"}]}]

    findings = reconcile_invoice(
        invoice,
        po,
        receipts,
        linked_po_number="PO-2026-0105",
        line_links={0: 1, 1: 2},  # Explicit owner-reviewed line links; invoice has no SKU/PO identifier.
    )

    assert [finding.code for finding in findings] == ["PO_NOT_PRINTED_ON_INVOICE"]
