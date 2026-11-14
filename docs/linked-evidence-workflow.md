# Linked Evidence Workflow: Three-Way Checks and LLM Answers

This guide explains how the project uses invoice, purchase order (PO), and goods-receipt (GR) links for two separate paths: a deterministic Python check and a natural-language answer from a selected language model. It describes the current demo and its limits; it does not describe an autonomous accounting agent or a production batch service.

For the deterministic result fields, see [three-way-match.md](three-way-match.md). For the CSV link and evidence-state design, see [manifest-design.md](manifest-design.md).

## Two commands, two jobs

Run commands from the project root with the project virtual environment activated.

### Deterministic three-way check

Python extracts candidate invoice fields, resolves the linked PO and receipts, runs the implemented reconciliation rules, and prints a JSON result with citations and review reasons. It does not call an answer model.

```powershell
python examples\three_way_match.py --invoice 004_q04
python examples\three_way_match.py --invoice 004_q04.pdf
python examples\three_way_match.py --po PO-2026-0104
```

The invoice argument can be an allow-listed case ID or filename, with or without `.pdf`, or a valid path. The input must resolve to a row in `eval/working_set.csv`. A PO may map to multiple invoice candidates; the CLI lists them and requires a separate invoice choice rather than combining claims. The Python path can report duplicate invoice numbers across the allow-listed invoices.

### Linked LLM question

The answer command requires one invoice or exact PO input plus a question. Python resolves the input first, gathers the linked evidence, and then sends those passages to the configured model.

```powershell
python examples\answer_linked_question.py --invoice 004_q04 "Compare the invoice quantity with the quantity received. Is there a mismatch? Give the quantities and cite both documents."
python examples\answer_linked_question.py --po PO-2026-0104 "Compare the invoice quantity with the quantity received. Is there a mismatch? Give the quantities and cite both documents."
python examples\answer_linked_question.py --invoice 002_q02 "What total and currency are printed on this invoice?"
```

The invoice input accepts an exact case ID or filename, with or without `.pdf`, or an allow-listed path. A PO linked to multiple invoices requires the user to choose one. A row marked `needs_review` is blocked until a person confirms the link. If a required source chunk is missing from Chroma, the command stops with an error before generation.

The current linked answer path is not a tool-calling agent. The question does not select arbitrary files or tools. The Python code uses `data/document_links.csv` to identify one invoice and its PO/receipt IDs, then fetches Chroma chunks by those exact source IDs. The model receives the selected document context, question, and labeled evidence passages; it does not open PDFs or CSVs itself. The application checks that returned citation IDs exist. For comparison questions, it also requires citations to both invoice and receipt evidence. These checks do not prove that every statement or amount is correct.

## Which files provide evidence

- `eval/working_set.csv` allow-lists invoices for the deterministic three-way command.
- `eval/review_queue.csv` contains owner-reviewed link candidates and review notes used by the deterministic loader. It is not included in the model prompt as expected-answer data.
- `data/document_links.csv` maps the linked-answer input to an invoice source, PO numbers, receipt IDs, and a link status. The linked-answer code refuses rows marked `needs_review`.
- The source invoice PDF provides invoice claims; `purchase_orders.json` provides PO records; `receipts.json` provides received quantities. The loader uses exact record IDs and `po_number` links; similarity search does not decide which accounting records belong together.
- Chroma stores evidence text chunks with source metadata. The linked answer cites the PDF page or JSON record associated with each supplied evidence ID.

If the PO links to multiple invoices, the model is not given all those invoice PDFs for a duplicate search. The duplicate-invoice check is a separate deterministic Python feature. A prompt asking the LLM whether an invoice is a duplicate cannot make the linked answer path search documents it did not receive.

## Answer model settings

`config.yaml` selects one answer provider for a run:

```yaml
answer:
  provider: ollama # or openai
  ollama_model: phi4-mini:latest
  openai_model: gpt-5.4-mini
  context: 4096
```

`answer.provider` selects Ollama or OpenAI for answer generation. The embedding model and Chroma index stay local. When OpenAI is selected, the app sends the question and selected evidence passages to the OpenAI API. The API key is loaded from `.env`. The CLI reports the provider and model in `answer_model`.

The system instruction limits answers to the supplied invoice, PO, and receipt evidence. For quantity comparisons, it requires the invoice and receipt quantities and citations. It tells the model to abstain when evidence or links are uncertain, and not to invent values or links. A PO match by itself does not establish that an invoice is a duplicate.

The JSON output includes `case_id`, `input`, `answer_model`, `answer`, `abstained`, `citations`, and `evidence_sources`. The application checks that citations refer to supplied evidence. For quantity comparisons, it also checks for invoice and receipt citations. Those checks do not confirm that the answer is factually correct.

## What the latest four-case check found

The check used `002_q02`, `004_q04`, `013_b01`, and `010_q10`. Python ran the three-way command on all four. OpenAI `gpt-5.4-mini` and local Ollama `phi4-mini:latest` received the same q02, q04, and b01 questions using the same exact-linked evidence path. Both q10 commands stopped before generation because its invoice chunk was not indexed. These four synthetic cases are observations, not a corpus accuracy estimate.

| Case | Python three-way output | OpenAI `gpt-5.4-mini` | Ollama `phi4-mini:latest` |
|---|---|---|---|
| `002_q02` | No findings; review not required. | Returned USD 396.95 and cited invoice plus PO. The captured answer had replacement characters around the currency symbol; the missing glyph cannot be recovered. | Returned `$396.95 USD` and cited the invoice page. The symbol rendered normally. |
| `004_q04` | Flagged `PO_GR_QTY_MISMATCH` and `QTY_EXCEEDS_RECEIVED`; review required. | Reported 50 invoiced versus 30 received for copy paper and 8 versus 8 for sticky notes; cited invoice and receipt. | Reported 50 versus 30 for copy paper and said the invoice quantity was 20 more; cited invoice and receipt. It did not mention sticky notes. |
| `013_b01` | Recognized EUR but missed invoice number, printed PO, lines, subtotal, tax, and total; review required. | Returned invoice `BF-2026/0401`, PO `PO-2026-0111`, EUR, and `514,08` from invoice text. Currency glyph appeared as a replacement character. | Returned the same requested values from invoice text. Currency glyph appeared as a replacement character. |
| `010_q10` | Unsupported extraction because the scan has no selectable text. | Stopped with `Linked evidence is not indexed for 010_q10: 010_q10`; no API answer was produced. | Stopped with the same missing-index error; no local-model answer was produced. |

Both models received the same case ID, question, linked evidence, and system instruction for q02, q04, and b01; only the provider and model changed. Both answered q04 using the linked evidence. For b01, both returned the requested values from the invoice page while the structured parser still failed to extract them. The model answers do not change or validate the parser result.

## Adding new files

New files must be registered, linked to their PO and receipt, and indexed in Chroma before the answer command can use them. A person reviews uncertain links and parser results. Scanned PDFs need OCR, which v1 does not include. The project has no automatic batch-ingestion command.
