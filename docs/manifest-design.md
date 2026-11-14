# Manifest and evidence status

This guide explains the status labels used for document links. The generated `data/raw/invoice-agent/manifest.json` lists synthetic cases; it is not the runtime link map.

## Source evidence and evaluation labels

Invoice PDFs, purchase order records, and goods-receipt records are source evidence. Ground-truth JSON is used only to compare evaluation results. It is not indexed in Chroma or used by answer generation or reconciliation.

## Evidence link states

Each relationship, such as invoice-to-PO or PO-to-receipt, has its own status:

| Status | Meaning |
|---|---|
| `available` | The linked source record was found. Its values may still differ from the other records. |
| `missing` | The supplied sources were checked, but the record was not found. |
| `ambiguous` | More than one record could match, so a person must choose. |
| `conflicting` | The sources or identifiers disagree, so the link or result needs review. |
| `not_reviewed` | The relationship has not been checked. This does not mean evidence is missing. |

## Status values used by the current code

These design labels differ from the runtime values. In `data/document_links.csv`, `listed` allows the linked-answer command to use a row, while `needs_review` blocks it until a person confirms the link. The deterministic loader uses `linked`, `missing`, `unreviewed`, `ambiguous`, `conflicting`, or `record_missing` for invoice-to-PO resolution. It reports receipt status as `available`, `missing`, `not_required`, or `unknown`.

An available link means the record was found; it does not mean the invoice, PO, and receipt agree. The reconciliation output reports value differences separately.
