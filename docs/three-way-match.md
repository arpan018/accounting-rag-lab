# Local three-way match example

This local learning flow compares one invoice candidate with its purchase order (PO) and goods receipts (GRs). It uses exact `po_number` links to load source records and deterministic `Decimal` rules to identify differences. It does not send documents to a model or make a final accounting decision.

Run from the project folder with the virtual environment:

```powershell
.\.venv\Scripts\python.exe examples\three_way_match.py --invoice invoices\001_q01.pdf
.\.venv\Scripts\python.exe examples\three_way_match.py --po PO-2026-0101
```

An invoice path must appear in `eval/working_set.csv`. If a PO number has more than one invoice candidate, the PO run lists the candidates and asks for one invoice file to be selected in a separate run. If an invoice does not print its PO number, the loader can use a separately reviewed link and still reports `PO_NOT_PRINTED_ON_INVOICE`.

The JSON output includes extracted candidate fields, the selected PO and GR record IDs, evidence citations, deterministic findings, a compact line-match count, calculation notes, extraction warnings, and whether human review is required. It does not print a full mapping row for every invoice item. Line-specific mismatch or unresolved details appear in `findings`; the match count shows how many invoice lines linked to PO lines. A unique one-to-one quantity/price mapping is not itself a discrepancy. Because distinct products can share a quantity and price, this matching rule should be evaluated before use outside the synthetic corpus. A scanned invoice such as `010_q10.pdf` remains unsupported without OCR.

`human_review_reasons` contains plain-language explanations for every run that sets `requires_human_review` to true. `first_pass_review` carries the existing reviewer annotation from the review queue. A missing discount is recorded under `calculation_notes` when zero is assumed for arithmetic; it is not an extraction warning.

The parser handles the current Quillfeather USD text layout. Other vendor layouts can return partial candidates or unresolved line links. Exact word/identifier extraction does not certify correctness; compare evidence and route missing, conflicting, uncertain, arithmetic, and receipt cases to a person. No tolerance, conversion, or rounding rule is added by this example.
