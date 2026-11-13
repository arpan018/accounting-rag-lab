"""Answer one question using exact invoice/PO/GR links, not similarity alone."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.env_loader import load_env_file  # noqa: E402
from src.generation import answer_with_evidence  # noqa: E402
from src.linked_evidence import (  # noqa: E402
    fetch_case_evidence,
    load_document_links,
    resolve_invoice_input,
    resolve_po_input,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Answer from an invoice and its linked PO/GR evidence.")
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--invoice", help="Allow-listed invoice path or exact file name, e.g. 004_q04 or 004_q04.pdf")
    input_group.add_argument("--po", help="Exact PO number, e.g. PO-2026-0104")
    parser.add_argument("question", help="Question to answer from linked source documents")
    args = parser.parse_args()

    with (PROJECT_ROOT / "config.yaml").open(encoding="utf-8") as handle:
        import yaml

        config = yaml.safe_load(handle)
    ollama = config["ollama"]
    answer_settings = config["answer"]
    load_env_file(PROJECT_ROOT / ".env")
    chroma = config["chroma"]
    client = __import__("chromadb").PersistentClient(path=str(PROJECT_ROOT / chroma["persist_directory"]))
    collection = client.get_collection(chroma["collection_name"])
    links = load_document_links(PROJECT_ROOT / "data/document_links.csv")
    try:
        if args.invoice:
            selected = resolve_invoice_input(args.invoice, links)
            supplied_identifier = f"invoice file {args.invoice}"
        else:
            candidates = resolve_po_input(args.po, links)
            if len(candidates) > 1:
                print(json.dumps({
                    "status": "invoice_selection_required",
                    "po_number": args.po,
                    "invoice_candidates": [item.invoice_source for item in candidates],
                    "message": "This PO is linked to multiple invoices. Rerun with --invoice and choose one file.",
                }, indent=2))
                return 2
            selected = candidates[0]
            supplied_identifier = f"purchase order {args.po}"
        evidence = fetch_case_evidence(selected.case_id, links, collection)
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))

    selected_context = (
        f"{supplied_identifier}; case {selected.case_id}; invoice file {selected.invoice_source}; "
        f"POs {', '.join(selected.po_numbers) or 'not listed'}"
    )
    answer = answer_with_evidence(
        args.question,
        evidence,
        model=(answer_settings["openai_model"] if answer_settings["provider"] == "openai" else answer_settings["ollama_model"]),
        provider=answer_settings["provider"],
        base_url=ollama["base_url"],
        num_ctx=answer_settings["context"],
        identifier_context=selected_context,
    )
    provider_label = "OpenAI API" if answer_settings["provider"] == "openai" else "Ollama"
    model_name = answer_settings["openai_model"] if answer_settings["provider"] == "openai" else answer_settings["ollama_model"]
    print(json.dumps({
        "case_id": selected.case_id,
        "input": {"invoice": args.invoice, "po": args.po},
        "answer_model": f"{provider_label} / {model_name}",
        "answer": answer.text,
        "abstained": answer.abstained,
        "citations": [citation.format() for citation in answer.citations],
        "evidence_sources": [item.citation.format() for item in evidence],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
