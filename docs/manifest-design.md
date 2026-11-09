# Manifest and evidence-status design

This document defines how the project tracks source documents and their links. The source corpus stays under ignored `data/raw/`; this design does not copy or modify it.

## Separate source evidence from expected answers

Invoices, purchase orders (POs), and goods receipts (GRs) are source evidence. Ground-truth labels are a separate evaluation reference: use them to check extraction, retrieval, and reconciliation outputs, never as RAG chunks or answer context. The raw package `manifest.json` is an inventory of generated cases, not the project's validated evidence manifest.

## Evidence link states

Each relationship is recorded independently (for example, invoice-to-PO and PO-to-GR):

| Status | Meaning | Example |
|---|---|---|
| `available` | A specific source record was located and linked. | Invoice prints `PO-2026-0114`; matching PO record is present. |
| `missing` | The evidence was checked for and is not present in the supplied source set. | No receipt record for a PO after checking the receipt inventory. |
| `ambiguous` | More than one plausible record exists; a human must resolve the link. | Two PO records could match an invoice. |
| `conflicting` | Sources or identifiers disagree in a way that prevents a safe link or conclusion. | Invoice and linked PO show different currencies. |
| `not_reviewed` | The relationship has not yet been checked. Do not interpret this as missing. | A case awaiting source inspection. |

`available` means the evidence record exists, not that its values agree. A price or quantity variance is recorded as a reconciliation finding while the evidence link can remain `available`. Keep invoice-stated identifiers distinct from inferred or proposed links, and retain the source and review provenance for either.

## Example record (illustrative, not an evaluation label)

```yaml
case_id: 005_q05
source_documents:
  - document_id: invoice-005_q05
    type: invoice
    path: data/raw/invoice-agent/invoices/005_q05.pdf
    provenance: synthetic invoice-agent corpus
links:
  invoice_to_po:
    status: available
    source: expected PO candidate in the supplied case reference; invoice itself has no PO number
    target_document_id: po-PO-2026-0105
    link_method: candidate_link_requires_review
  po_to_gr:
    status: available
    target_document_id: gr-GR-00006
review:
  status: not_reviewed
  reviewer: null
  note: Owner review is required before this case is treated as verified ground truth.
```

The example makes clear that the invoice does not state a PO number and that the candidate link is not a value extracted from the invoice. It is intentionally not owner-certified. Do not mark it reviewed based on this example.

## Provenance and evaluation separation

Every source record needs a stable ID, document type, relative path, corpus/source attribution, and page provenance when extracted. Expected values belong in a separate evaluation file keyed by case and field, with reviewer/status/source references. Preserve original strings; monetary normalization and comparison use `Decimal` created from strings with currency and rounding behavior explicit. Never include ground-truth files in ingestion or chunking inputs.
