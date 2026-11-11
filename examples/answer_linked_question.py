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
from src.linked_evidence import fetch_case_evidence, load_document_links  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Answer from an invoice and its linked PO/GR evidence.")
    parser.add_argument("case_id", help="Case key from data/document_links.csv")
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
    evidence = fetch_case_evidence(args.case_id, links, collection)
    answer = answer_with_evidence(
        args.question,
        evidence,
        model=(answer_settings["openai_model"] if answer_settings["provider"] == "openai" else answer_settings["ollama_model"]),
        provider=answer_settings["provider"],
        base_url=ollama["base_url"],
        num_ctx=answer_settings["context"],
    )
    provider_label = "OpenAI API" if answer_settings["provider"] == "openai" else "Ollama"
    model_name = answer_settings["openai_model"] if answer_settings["provider"] == "openai" else answer_settings["ollama_model"]
    print(json.dumps({
        "case_id": args.case_id,
        "answer_model": f"{provider_label} / {model_name}",
        "answer": answer.text,
        "abstained": answer.abstained,
        "citations": [citation.format() for citation in answer.citations],
        "evidence_sources": [item.citation.format() for item in evidence],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
