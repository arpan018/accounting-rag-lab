# Local three-way match example

Compare one invoice with its linked PO and goods receipts. The Python command follows exact `po_number` links and uses `Decimal` checks to report differences. It does not call an LLM or approve an invoice.

Run from the project folder with the virtual environment:

```powershell
.\.venv\Scripts\python.exe examples\three_way_match.py --invoice invoices\001_q01.pdf
.\.venv\Scripts\python.exe examples\three_way_match.py --invoice 001_q01
.\.venv\Scripts\python.exe examples\three_way_match.py --invoice 001_q01.pdf
.\.venv\Scripts\python.exe examples\three_way_match.py --po PO-2026-0101
```

The command accepts an allow-listed path, case ID, or exact filename, with or without `.pdf`. Each invoice must appear in `eval/working_set.csv`; invalid or ambiguous inputs return a readable error. If a PO has multiple invoice candidates, the CLI lists them and asks you to run the check again with one invoice selected. If an invoice does not print a PO number, the loader can use a separately reviewed link while leaving the printed PO field empty.

## Reading the JSON result

The result is a summary of candidate extraction and code checks, not an approval to pay. Its top-level fields are:

| Field | Meaning |
|---|---|
| `status`, `input` | Whether the check completed or stopped, and the invoice/PO input used. |
| `invoice_case_id`, `invoice_candidates` | Resolved case and any invoice choices associated with the input. |
| `invoice`, `purchase_order`, `receipts` | Candidate invoice fields and the linked PO/GR identities, summary values, and source locators. Missing candidate values can be `null`. |
| `findings` | Coded discrepancies or unresolved conditions, each with a short message. |
| `citations` | PDF page and JSON record locations used for the result. |
| `extraction_warnings`, `calculation_notes` | Missing/partial text information and calculation assumptions, kept separate. |
| `line_match_summary` | Counts for invoice lines, linked PO lines, and unresolved lines. The output does not print every internal line mapping. |
| `first_pass_review` | Existing owner note from the review queue. Read this alongside `findings`; it is not a computed conclusion and can differ from current findings. |
| `human_review_reasons`, `requires_human_review` | Why a person should inspect the case and the resulting review flag. |

Monetary candidate values are kept as source strings (or `null`) in the JSON. The reconciler uses `Decimal` from those strings. It adds no unstated tolerance, currency conversion, or rounding rule. A duplicate printed invoice number among the allow-listed PDFs can produce `DUPLICATE_INVOICE_NUMBER` and require review.

`findings` lists mismatches and unresolved links. `line_match_summary` shows how many invoice lines linked to PO lines, but it does not show each line mapping. A unique quantity-and-price match is treated as a link, not a discrepancy. Different products can share those values, so review this rule before using it beyond the synthetic data.

When an invoice omits a discount, the calculation assumes zero and records that assumption in `calculation_notes`.

The parser handles the current Quillfeather USD layout. Other vendor layouts may produce incomplete fields or unresolved lines. Review missing or uncertain values and any amount or receipt mismatch against the source documents.
