# Accounting Document Intelligence Lab

A local learning project for comparing invoice claims with purchase orders (POs) and goods-receipt (GR) evidence. The planned MVP extracts text from selectable PDFs, retrieves source-backed evidence, answers with source/page citations, and applies deterministic Python checks to flag discrepancies for human review.

This is a learning and system-design project, not an autonomous accounting workflow. See [`AGENTS.md`](AGENTS.md) for project instructions and [`.work/project-plan.md`](.work/project-plan.md) for the detailed scope and phases.

## Portfolio framing

This project prototypes the document-intelligence and reconciliation core that could sit inside a larger CPA/accounting platform. It demonstrates taking an invoice through evidence extraction, PO/receipt matching, deterministic checks, and human review. It is not a complete practice-management product: ERP connectors, a production API/UI, cloud deployment, OCR, and operational monitoring remain outside this prototype.

## Current status

Bootstrap and initial corpus review are complete. T08 adds selectable-PDF extraction and provenance-preserving chunking; the active learning scope ends at invoice case `031_k09`. The current implementation is local and performs no OCR. The project environment uses Python 3.14.3 with the approved dependencies PyMuPDF, ChromaDB, JupyterLab, and pytest. The local embedding model selected for T10 is `embeddinggemma-2:270m`; `phi4-mini:latest` remains the local CLI smoke-test model. Core generation-model selection is still open. The synthetic learning corpus is under `data/raw/invoice-agent/` and is excluded from Git.

## Learning dataset

The full synthetic invoice-agent dataset was generated locally from the [`invoice-agent` PyPI package](https://pypi.org/project/invoice-agent/) using its synthetic-data extra. The source is [superintelligenceco/invoice-agent](https://github.com/superintelligenceco/invoice-agent); the published [QuickStart](https://superintelligenceco.github.io/invoice-agent/quickstart/) describes the generator. The generated set contains invoice PDFs, ground-truth JSON, a manifest, purchase orders, and receipts. Credit the source when discussing or sharing this project; the raw corpus remains ignored and local.

## Set up the project environment

Use the verified Python 3.14.3 executable to create a project-only virtual environment. In PowerShell:

```powershell
& 'C:\Users\arpan\AppData\Local\Python\bin\python.exe' -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

This keeps packages in `.venv` and leaves global Python unchanged. To start JupyterLab after setup:

```powershell
.\.venv\Scripts\python.exe -m jupyter lab
```

## Planned learning path

Work through the tasks in [`.work/task-board.md`](.work/task-board.md), one task at a time. The planned phases cover environment setup, corpus and manifest review, text extraction and chunking, Decimal-based reconciliation, local embeddings and Chroma, cited retrieval and generation, evaluation, and a v1 review.

Money must use Python `Decimal` constructed from source strings. Model-extracted fields are candidates only; owner-verified source values and human review remain the authority for business conclusions.

## Data and privacy

The `.gitignore` excludes `.venv`, `.env`, `.work`, raw data, local indexes, embeddings, processed data, and common Python/notebook artifacts. Keep source records and secrets local. Review derived and evaluation artifacts before any decision to track them.
