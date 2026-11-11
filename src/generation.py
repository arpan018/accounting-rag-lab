"""Local Ollama answer generation that accepts retrieved evidence only."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from src.retrieval import Citation, RetrievedEvidence


ABSTENTION = "I can't answer from the available documents."


class GenerationError(RuntimeError):
    """Raised when the local model cannot return an answer."""


@dataclass(frozen=True)
class GroundedAnswer:
    text: str
    citations: tuple[Citation, ...]
    abstained: bool


# Number evidence passages so citations can be checked against retrieved items.
def build_evidence_prompt(question: str, evidence: Sequence[RetrievedEvidence]) -> str:
    blocks = []
    for index, item in enumerate(evidence, start=1):
        blocks.append(f"[E{index}] {item.citation.format()}\n{item.text}")
    return f"Question:\n{question}\n\nRetrieved evidence:\n" + "\n\n".join(blocks)


# Call only loopback Ollama and replace uncited or ungrounded references with abstention.
def answer_with_evidence(
    question: str,
    evidence: Sequence[RetrievedEvidence],
    *,
    model: str,
    base_url: str = "http://127.0.0.1:11434",
    num_ctx: int = 4096,
    timeout_seconds: int = 180,
) -> GroundedAnswer:
    if not question.strip():
        raise ValueError("question must not be empty")
    if not evidence:
        return GroundedAnswer(ABSTENTION, (), True)
    endpoint = urlsplit(base_url)
    if endpoint.scheme != "http" or endpoint.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Only a local Ollama endpoint is allowed")
    if not model or num_ctx < 1:
        raise ValueError("model name and positive context length are required")

    system = (
        "Answer only from the supplied invoice, purchase order, and goods-receipt evidence. "
        "For a question comparing invoiced and received quantities, state the invoice quantity and "
        "receipt quantity, then compare them. Cite both the invoice evidence and receipt evidence. "
        "If a needed document or value is missing, or a document link is uncertain, abstain. "
        f"If it does not support an answer, reply exactly: {ABSTENTION} "
        "Cite each factual claim with the supplied evidence IDs like [E1]. "
        "Use only supplied IDs. Do not infer document links, invent values, or treat a PO match alone as a duplicate invoice."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": build_evidence_prompt(question, evidence)},
        ],
        "stream": False,
        "options": {"num_ctx": num_ctx, "temperature": 0},
    }
    request = Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GenerationError(f"Local Ollama answer request failed: {exc}") from exc

    message = result.get("message", {}) if isinstance(result, dict) else {}
    raw_answer = message.get("content", "").strip() if isinstance(message, dict) else ""
    if not raw_answer or raw_answer.casefold() == ABSTENTION.casefold():
        return GroundedAnswer(ABSTENTION, (), True)

    ids = [int(value) for value in re.findall(r"\[E(\d+)\]", raw_answer)]
    if not ids or any(value < 1 or value > len(evidence) for value in ids):
        return GroundedAnswer(ABSTENTION, (), True)
    unique_ids = tuple(dict.fromkeys(ids))
    comparison_question = bool(re.search(r"\b(compare|all .* units|invoiced|received|discrepancy|mismatch)\b", question, re.IGNORECASE))
    if comparison_question:
        cited_types = {evidence[value - 1].document_type for value in unique_ids}
        has_invoice = any("invoice" in value for value in cited_types)
        has_receipt = any(value in {"goods_receipt", "receipt"} for value in cited_types)
        if not has_invoice or not has_receipt:
            return GroundedAnswer(ABSTENTION, (), True)
    citations = tuple(evidence[value - 1].citation for value in unique_ids)
    return GroundedAnswer(raw_answer, citations, False)
