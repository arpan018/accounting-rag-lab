# Accounting Document Intelligence Lab

A local learning project for comparing invoice claims with purchase orders (POs) and goods-receipt (GR) evidence. The planned MVP extracts text from selectable PDFs, retrieves source-backed evidence, answers with source/page citations, and applies deterministic Python checks to flag discrepancies for human review.

This is a learning and system-design project, not an autonomous accounting workflow. Start with the guides in [`docs/`](docs/): they cover data links, the deterministic three-way check, and the linked LLM answer flow.

## Current status

The current implementation extracts text from selectable PDFs, builds a local Chroma index with Ollama embeddings, and runs deterministic invoice, PO, and receipt checks. Python selects the source chunks before sending a question to the configured answer model.

Local Ollama `phi4-mini:latest` is the default answer model. `config.yaml` also allows OpenAI `gpt-5.4-mini`. Both models answered the same three questions in a small synthetic check. This is not a corpus accuracy result. OCR is not implemented.

The project uses Python 3.14 and the dependencies listed here: PyMuPDF, ChromaDB, JupyterLab, pytest, and Pydantic. The local embedding model is `embeddinggemma-2:270m`. The synthetic corpus is stored under `data/raw/invoice-agent/` and excluded from Git.

## Learning dataset

The full synthetic invoice-agent dataset was generated locally from the [`invoice-agent` PyPI package](https://pypi.org/project/invoice-agent/) using its synthetic-data extra. The source [QuickStart](https://superintelligenceco.github.io/invoice-agent/quickstart/) describes the generator. The generated set contains invoice PDFs, ground-truth JSON, a manifest, purchase orders, and receipts.

## Set up the project environment

With Python 3.14 available in PowerShell, create a project-only virtual environment and install the listed packages:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If `python --version` does not report Python 3.14, use the path to your Python 3.14 executable in the `venv` command. This keeps packages in `.venv` and leaves global Python unchanged.

## Project guides

- [Manifest design](docs/manifest-design.md) explains source links, review states, and evaluation separation.
- [Three-way match](docs/three-way-match.md) explains the deterministic command and its JSON output.
- [Linked evidence workflow](docs/linked-evidence-workflow.md) explains how the LLM answer path gathers and cites invoice/PO/receipt evidence, including the small OpenAI check and its limits.

Money is parsed and compared with Python `Decimal` built from source strings. Model-extracted fields are candidates. Owner-verified source values and human review remain the basis for business conclusions.

## Data and privacy

The `.gitignore` excludes `.venv`, `.env`, `.work`, raw data, local indexes, embeddings, processed data, and common Python/notebook artifacts. Keep source records and secrets local. Review derived and evaluation artifacts before any decision to track them.
