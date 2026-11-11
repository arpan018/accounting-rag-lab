# Learning Notes

Use these notes to explain what each project phase teaches. Keep examples small and tie each new idea to the invoice/PO/GR evidence flow.

## Bootstrap and Python environments

- A virtual environment keeps this project's installed packages separate from global Python. Use `.venv` and its Python executable for project commands.
- `requirements.txt` is the approved package list. Do not add libraries or install them globally without owner approval.
- `config.yaml` holds non-secret settings. Do not put API keys or credentials in it.

## Planned learning sequence

1. **Files, CSV, and provenance:** inspect a licensed source set; record document type, source, links, and evidence status in a manifest.
2. **PDF text and pages:** use PyMuPDF for selectable text; preserve file/page provenance and recognize empty or unsupported scanned pages without adding OCR.
3. **Reusable Python modules:** move repeatable logic into `src/`; keep notebooks for inspection and learning.
4. **Money and deterministic checks:** parse monetary strings with `Decimal`, keep currency explicit, and make rounding rules reviewable. Never use binary float for money.
5. **Embeddings and retrieval:** send text to an approved local Ollama embedding model, store explicit vectors and provenance in Chroma, and retrieve evidence for a question.
6. **Grounded answers and evaluation:** check citations and unsupported answers; measure retrieval, extraction, reconciliation, and answer correctness separately.

## Review habits

- Preserve original source text beside normalized values.
- Treat model output as an unverified candidate until checked against source evidence and deterministic rules.
- Ask a person to resolve missing, ambiguous, conflicting, material, or low-confidence cases.
- Distinguish synthetic tests from evaluation on owner-verified real records. Do not claim corpus accuracy when the reference labels are unverified.

## Pydantic schemas for accounting records

Pydantic `BaseModel` classes describe the fields a record must have and validate incoming Python/JSON data. In this project, `PurchaseOrderRecord` and `GoodsReceiptRecord` mirror the source JSON keys; a `SourceLocator` is added by the loader because the JSON record itself does not identify its file location. `extra="forbid"` catches unexpected fields so a changed source format is visible instead of silently ignored.

Money and quantity fields stay as strict source strings such as `"12.50"` or `"12,5"`. A schema validator checks that each string is parseable using the declared separators, while `decimal_value()` calls the existing `parse_decimal()` function to produce a Python `Decimal` when calculation is needed. This keeps the original spelling available for audit and rejects floats. A valid Pydantic object only proves that its shape and types passed validation; it does not prove that the invoice is correct or agrees with a PO or receipt. Deterministic reconciliation and human review still decide those questions.

## Exact record links versus vector search

The source PO and receipt JSON records both have a `po_number`. The record loader uses that exact identifier to fetch the PO and every receipt linked to it. For an invoice, a printed PO number is an exact candidate; if it is absent, a separate reviewed link can supply a candidate while the invoice's omission remains visible. A PO can have multiple invoices or receipts, so the loader returns all candidates/records instead of assuming a one-to-one relationship. Chroma similarity helps find relevant passages, but it does not establish that two accounting records belong together.

## Ground truth and the business use case

An invoice is a supplier's claim: “we supplied these items/services and you owe this amount.” In a real purchasing organization, the independent records used to check that claim usually come from separate systems:

- **Purchase order (PO):** the buyer's approved commitment: supplier, items/services, quantities, prices, and terms.
- **Goods receipt (GR):** warehouse or receiving team's record of what physically arrived. For services, use an approved service-entry or acceptance record instead of pretending there was a physical receipt.
- **Accounts-payable (AP) transaction:** the invoice received and entered into the ERP/accounting system, including posting or payment status. This is useful for workflow outcomes, but it can contain the same data-entry mistakes being investigated, so it is not automatically truth.

For field-extraction evaluation, a person verifies each labeled value against the invoice itself and records its source/page. For reconciliation, trusted PO and receiving/acceptance records provide the independent comparison; the expected discrepancy is determined by explicit business rules and then reviewed by an owner. A final posted/paid/held outcome can be additional evidence, not a substitute for checking the underlying documents and records.

**Example:** an invoice says 10 boxes arrived at $12 each, plus $9.60 tax, for $129.60. The approved PO authorizes 10 boxes at $12, but the warehouse GR records only 8. Extraction ground truth confirms the invoice's own 10-box claim from its PDF. Reconciliation ground truth comes from the separate PO and GR records; a deterministic three-way check should flag that the billed quantity exceeds the recorded receipt and route it for human review. It should not silently change the invoice to 8 boxes or treat the invoice PDF as proof that 10 arrived.

## Natural invoices and extraction tools

Real supplier invoices can be valuable later, but an invoice PDF alone rarely supplies the linked PO/GR records and independently verified labels needed to measure a three-way reconciliation system. Real documents can also include private account, tax, pricing, and contact details. Layout differences are a technical challenge, not the main reason to start with synthetic data. Natural data is appropriate after the organization authorizes its use, sensitive fields are handled safely, and matching source records and human-verified labels are available.

`invoice2data` is an invoice extraction tool: it reads a PDF/image and applies vendor/layout templates to produce structured fields. It can help create candidate values or serve as an extraction baseline; it does not generate independent ground truth, supply PO/GR records, or certify its own output. Templates and field mappings still need human review, especially when layouts or business meanings differ. OCR and its optional AI/template-generation features remain outside this project's v1 scope.

## Reference project: what was reused

The `invoice-agent` PyPI package was installed temporarily with its synthetic-data extra only to generate the local learning corpus. We retained the generated PDFs, labels, manifest, POs, and receipts, and cite the source in the README. We removed the temporary generator environment. We did not adopt its application code, extraction/matching rules, tolerance values, evaluator, or reported performance; this project must implement and evaluate its own pipeline.
