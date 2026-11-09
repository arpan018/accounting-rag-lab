"""Deterministic checks that numeric answer claims appear in cited evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from src.generation import GroundedAnswer
from src.reconciliation import parse_decimal
from src.retrieval import RetrievedEvidence


NUMBER_PATTERN = re.compile(r"(?<![A-Za-z0-9])[-+]?\d+(?:[.,]\d+)*(?![A-Za-z0-9])")
CITATION_PATTERN = re.compile(r"\[E\d+\]")


@dataclass(frozen=True)
class NumericValidation:
    supported: bool
    checked_values: tuple[str, ...]
    unsupported_values: tuple[str, ...]
    ambiguous_values: tuple[str, ...]


# Compare answer numbers with cited source numbers using Decimal, never binary float.
def validate_numeric_claims(
    answer: GroundedAnswer,
    evidence: Sequence[RetrievedEvidence],
) -> NumericValidation:
    if answer.abstained:
        return NumericValidation(True, (), (), ())

    answer_values = tuple(NUMBER_PATTERN.findall(CITATION_PATTERN.sub("", answer.text)))
    if not answer_values:
        return NumericValidation(True, (), (), ())
    cited_sources = {citation.format() for citation in answer.citations}
    cited_evidence = [item for item in evidence if item.citation.format() in cited_sources]
    source_values = [
        token
        for item in cited_evidence
        for token in NUMBER_PATTERN.findall(item.text)
    ]

    checked: list[str] = []
    unsupported: list[str] = []
    ambiguous: list[str] = []
    source_variants = [(token, _decimal_variants(token)) for token in source_values]
    for token in answer_values:
        variants = _decimal_variants(token)
        if len(variants) > 1:
            ambiguous.append(token)
        elif variants and any(variants.intersection(values) for _, values in source_variants):
            checked.append(token)
        else:
            unsupported.append(token)
    return NumericValidation(not unsupported and not ambiguous, tuple(checked), tuple(unsupported), tuple(ambiguous))


def _decimal_variants(value: str) -> set[Decimal]:
    """Return strict Decimal interpretations for dot/comma decimal or grouping forms."""
    variants: set[Decimal] = set()
    for decimal_separator in (".", ","):
        for grouping_separator in (None, "," if decimal_separator == "." else "."):
            try:
                variants.add(
                    parse_decimal(
                        value,
                        decimal_separator=decimal_separator,
                        grouping_separator=grouping_separator,
                    )
                )
            except (TypeError, ValueError):
                continue
    return variants
